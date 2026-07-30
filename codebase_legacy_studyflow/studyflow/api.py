"""Small JSON API and static-file server for the prototype."""

from __future__ import annotations

import json
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import config
from .ai_service import AIService
from .repository import TaskRepository
from .rule_engine import build_dashboard, enrich_and_rank, parse_datetime


PUBLIC_DIR = config.CODEBASE_DIR / "public"
MAX_BODY_BYTES = 1_000_000


class Application:
    def __init__(self, repository: TaskRepository | None = None, ai: AIService | None = None):
        self.repository = repository or TaskRepository(config.DB_PATH)
        self.ai = ai or AIService(
            api_key=config.GEMINI_API_KEY,
            model=config.GEMINI_MODEL,
            timeout_seconds=config.AI_TIMEOUT_SECONDS,
            trace_path=config.AI_TRACE_PATH,
            trace_full_input=config.AI_TRACE_FULL_INPUT,
        )


APP = Application()


class Handler(BaseHTTPRequestHandler):
    server_version = "StudyFlow/0.1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"[StudyFlow] {self.address_string()} - {format % args}")

    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message}, status)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Content-Length không hợp lệ.") from error
        if length <= 0:
            return {}
        if length > MAX_BODY_BYTES:
            raise ValueError("Request body quá lớn.")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Body phải là JSON hợp lệ.") from error
        if not isinstance(payload, dict):
            raise ValueError("Body JSON phải là một object.")
        return payload

    def _task_id(self, path: str, suffix: str = "") -> int | None:
        match = re.fullmatch(rf"/api/tasks/(\d+){suffix}", path)
        return int(match.group(1)) if match else None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/health":
                self._json(
                    {
                        "status": "ok",
                        "ai_configured": APP.ai.configured,
                        "ai_model": APP.ai.model,
                        "prototype": "Mock — VLearn/Discord integrations are simulated",
                    }
                )
                return
            if parsed.path == "/api/tasks":
                query = parse_qs(parsed.query)
                now = parse_datetime(query.get("now", [None])[0])
                self._json({"tasks": enrich_and_rank(APP.repository.list_tasks(), now)})
                return
            if parsed.path == "/api/dashboard":
                query = parse_qs(parsed.query)
                now = parse_datetime(query.get("now", [None])[0])
                self._json(build_dashboard(APP.repository.list_tasks(), now))
                return
            task_id = self._task_id(parsed.path)
            if task_id is not None:
                task = APP.repository.get_task(task_id)
                if not task:
                    self._error(404, "Không tìm thấy task.")
                else:
                    self._json(task)
                return
            self._serve_static(parsed.path)
        except ValueError as error:
            self._error(400, str(error))
        except Exception as error:
            print(f"[StudyFlow] unexpected error: {error!r}")
            self._error(500, "Hệ thống gặp lỗi ngoài dự kiến.")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self._body()
            if parsed.path == "/api/tasks":
                self._json(APP.repository.create_task(payload), HTTPStatus.CREATED)
                return
            if parsed.path == "/api/ai/parse-task":
                self._json(APP.ai.parse_task(str(payload.get("text", ""))))
                return
            task_id = self._task_id(parsed.path, "/check-in")
            if task_id is not None:
                task = APP.repository.check_in(task_id, payload)
                if not task:
                    self._error(404, "Không tìm thấy task.")
                else:
                    self._json(task)
                return
            self._error(404, "API endpoint không tồn tại.")
        except ValueError as error:
            self._error(400, str(error))
        except Exception as error:
            print(f"[StudyFlow] unexpected error: {error!r}")
            self._error(500, "Hệ thống gặp lỗi ngoài dự kiến.")

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        try:
            task_id = self._task_id(parsed.path)
            if task_id is None:
                self._error(404, "API endpoint không tồn tại.")
                return
            task = APP.repository.update_task(task_id, self._body())
            if not task:
                self._error(404, "Không tìm thấy task.")
            else:
                self._json(task)
        except ValueError as error:
            self._error(400, str(error))
        except Exception as error:
            print(f"[StudyFlow] unexpected error: {error!r}")
            self._error(500, "Hệ thống gặp lỗi ngoài dự kiến.")

    def _serve_static(self, requested_path: str) -> None:
        relative = "index.html" if requested_path == "/" else requested_path.lstrip("/")
        candidate = (PUBLIC_DIR / relative).resolve()
        try:
            candidate.relative_to(PUBLIC_DIR.resolve())
        except ValueError:
            self._error(403, "Đường dẫn không hợp lệ.")
            return
        if not candidate.is_file():
            self._error(404, "Không tìm thấy tài nguyên.")
            return
        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


def run() -> None:
    seeded = APP.repository.seed_if_empty()
    server = ThreadingHTTPServer((config.HOST, config.PORT), Handler)
    print(f"StudyFlow đang chạy tại http://{config.HOST}:{config.PORT}")
    print(f"AI: {'Gemini ' + config.GEMINI_MODEL if APP.ai.configured else 'rule fallback (chưa có key)'}")
    if seeded:
        print("Đã tạo 4 task mock theo ngày hiện tại để demo.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng StudyFlow.")
    finally:
        server.server_close()
