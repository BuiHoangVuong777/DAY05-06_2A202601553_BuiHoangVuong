"""Gemini structured extraction with explicit, labelled fallback behaviour."""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


class AIService:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        trace_path: Path,
        trace_full_input: bool = False,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.trace_path = trace_path
        self.trace_full_input = trace_full_input

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _fallback(text: str, now: datetime) -> dict[str, Any]:
        lowered = text.lower()
        due = now + timedelta(days=3)
        if "hôm nay" in lowered:
            due = now.replace(hour=16, minute=59, second=0, microsecond=0)
        elif "ngày mai" in lowered or "mai " in f"{lowered} ":
            due = (now + timedelta(days=1)).replace(hour=16, minute=59, second=0, microsecond=0)
        importance = "high" if any(word in lowered for word in ("gấp", "quan trọng", "urgent")) else "medium"
        title = re.split(r"[,.;\n]", text.strip())[0][:180] or "Task mới"
        return {
            "title": title,
            "description": text.strip(),
            "course": "",
            "assignee": "",
            "due_at": due.isoformat(),
            "importance": importance,
            "confidence": 35,
            "ambiguity": "Fallback chỉ đoán deadline cơ bản; cần người dùng kiểm tra lại.",
            "clarification_question": "Bạn kiểm tra giúp deadline và người phụ trách trước khi lưu nhé.",
        }

    @staticmethod
    def _extract_output_text(response: dict[str, Any]) -> str:
        chunks: list[str] = []
        for step in response.get("steps", []):
            if step.get("type") != "model_output":
                continue
            for content in step.get("content", []):
                if content.get("type") == "text" and isinstance(content.get("text"), str):
                    chunks.append(content["text"])
        if not chunks:
            raise ValueError("Gemini không trả về model_output dạng text.")
        return "".join(chunks)

    @staticmethod
    def _validate(result: dict[str, Any], now: datetime) -> dict[str, Any]:
        title = str(result.get("title", "")).strip()[:180]
        if not title:
            raise ValueError("AI không trích xuất được tên task.")
        importance = result.get("importance")
        if importance not in {"low", "medium", "high"}:
            importance = "medium"
        due_at = str(result.get("due_at") or "").strip()
        if due_at:
            parsed = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            due_at = parsed.astimezone(timezone.utc).isoformat()
        else:
            due_at = (now + timedelta(days=3)).isoformat()
        return {
            "title": title,
            "description": str(result.get("description", "")).strip(),
            "course": str(result.get("course", "")).strip(),
            "assignee": str(result.get("assignee", "")).strip(),
            "due_at": due_at,
            "importance": importance,
            "confidence": max(0, min(100, int(result.get("confidence", 0)))),
            "ambiguity": str(result.get("ambiguity", "")).strip(),
            "clarification_question": str(result.get("clarification_question", "")).strip(),
        }

    def _write_trace(self, record: dict[str, Any]) -> None:
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self.trace_path.open("a", encoding="utf-8") as trace:
            trace.write(json.dumps(record, ensure_ascii=False) + "\n")

    def parse_task(self, text: str, now: datetime | None = None) -> dict[str, Any]:
        text = text.strip()
        if not text:
            raise ValueError("Hãy nhập mô tả task.")
        if len(text) > 2_000:
            raise ValueError("Mô tả task tối đa 2.000 ký tự.")
        current = now or datetime.now(timezone.utc)
        started = time.perf_counter()

        if not self.configured:
            output = self._fallback(text, current)
            return {
                "mode": "fallback",
                "model": None,
                "warning": "Chưa có GEMINI_API_KEY; kết quả là rule fallback và cần kiểm tra tay.",
                "task": output,
            }

        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Tên task ngắn, bắt đầu bằng động từ."},
                "description": {"type": "string", "description": "Chi tiết còn lại từ câu nhập."},
                "course": {"type": "string", "description": "Tên môn hoặc dự án; rỗng nếu không rõ."},
                "assignee": {"type": "string", "description": "Người phụ trách; rỗng nếu không rõ."},
                "due_at": {
                    "type": ["string", "null"],
                    "format": "date-time",
                    "description": "Deadline ISO 8601; null nếu hoàn toàn không suy ra được.",
                },
                "importance": {"type": "string", "enum": ["low", "medium", "high"]},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                "ambiguity": {"type": "string", "description": "Điểm mơ hồ quan trọng nhất; rỗng nếu không có."},
                "clarification_question": {
                    "type": "string",
                    "description": "Một câu hỏi lại ngắn khi confidence dưới 70; rỗng nếu đủ rõ.",
                },
            },
            "required": [
                "title",
                "description",
                "course",
                "assignee",
                "due_at",
                "importance",
                "confidence",
                "ambiguity",
                "clarification_question",
            ],
            "additionalProperties": False,
        }
        prompt = (
            "Trích xuất task học tập tiếng Việt. Không bịa môn, người phụ trách hay deadline. "
            "Nếu user dùng ngày tương đối, quy đổi theo thời điểm hiện tại. Nếu thiếu dữ kiện, "
            "để chuỗi rỗng, giảm confidence và hỏi đúng một câu làm rõ. "
            f"Thời điểm hiện tại UTC: {current.isoformat()}\nCâu nhập: {text}"
        )
        payload = {
            "model": self.model,
            "input": prompt,
            "store": False,
            "generation_config": {
                "thinking_level": "low",
                "max_output_tokens": 700,
            },
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            },
        }
        request = urllib.request.Request(
            INTERACTIONS_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        trace: dict[str, Any] = {
            "timestamp": current.isoformat(),
            "provider": "Google Gemini",
            "model": self.model,
            "input_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
        if self.trace_full_input:
            trace["input"] = text
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw_response = json.loads(response.read().decode("utf-8"))
            parsed = json.loads(self._extract_output_text(raw_response))
            task = self._validate(parsed, current)
            trace.update(
                {
                    "success": True,
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                    "output": task,
                    "usage": raw_response.get("usage", {}),
                }
            )
            self._write_trace(trace)
            return {
                "mode": "ai",
                "model": self.model,
                "interaction_id": raw_response.get("id"),
                "warning": "",
                "task": task,
            }
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
            trace.update(
                {
                    "success": False,
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                    "error": str(error),
                }
            )
            self._write_trace(trace)
            fallback = self._fallback(text, current)
            return {
                "mode": "fallback",
                "model": self.model,
                "warning": f"AI call lỗi ({type(error).__name__}); đã chuyển sang rule fallback.",
                "task": fallback,
            }
