"""SQLite persistence for tasks and quick progress check-ins."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


TASK_FIELDS = {
    "title",
    "description",
    "course",
    "assignee",
    "due_at",
    "importance",
    "status",
    "progress",
    "blocked_reason",
    "source",
}
VALID_STATUS = {"todo", "in_progress", "blocked", "done"}
VALID_IMPORTANCE = {"low", "medium", "high"}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def init_db(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    course TEXT NOT NULL DEFAULT '',
                    assignee TEXT NOT NULL DEFAULT '',
                    due_at TEXT,
                    importance TEXT NOT NULL DEFAULT 'medium',
                    status TEXT NOT NULL DEFAULT 'todo',
                    progress INTEGER NOT NULL DEFAULT 0,
                    blocked_reason TEXT NOT NULL DEFAULT '',
                    blocked_since TEXT,
                    source TEXT NOT NULL DEFAULT 'manual',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS checkins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    progress INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _validate(payload: dict[str, Any], partial: bool = False) -> dict[str, Any]:
        clean = {key: payload[key] for key in TASK_FIELDS if key in payload}
        if not partial and not str(clean.get("title", "")).strip():
            raise ValueError("Tên task không được để trống.")
        if "title" in clean:
            clean["title"] = str(clean["title"]).strip()
            if not clean["title"]:
                raise ValueError("Tên task không được để trống.")
            if len(clean["title"]) > 180:
                raise ValueError("Tên task tối đa 180 ký tự.")
        if "status" in clean and clean["status"] not in VALID_STATUS:
            raise ValueError("Trạng thái task không hợp lệ.")
        if "importance" in clean and clean["importance"] not in VALID_IMPORTANCE:
            raise ValueError("Độ quan trọng không hợp lệ.")
        if "progress" in clean:
            clean["progress"] = int(clean["progress"])
            if not 0 <= clean["progress"] <= 100:
                raise ValueError("Tiến độ phải từ 0 đến 100.")
        for key in ("description", "course", "assignee", "blocked_reason", "source"):
            if key in clean:
                clean[key] = str(clean[key] or "").strip()
        if "due_at" in clean and clean["due_at"]:
            datetime.fromisoformat(str(clean["due_at"]).replace("Z", "+00:00"))
        return clean

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def list_tasks(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._row(row)

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        clean = self._validate(payload)
        now = iso_now()
        values = {
            "title": clean["title"],
            "description": clean.get("description", ""),
            "course": clean.get("course", ""),
            "assignee": clean.get("assignee", ""),
            "due_at": clean.get("due_at") or None,
            "importance": clean.get("importance", "medium"),
            "status": clean.get("status", "todo"),
            "progress": clean.get("progress", 0),
            "blocked_reason": clean.get("blocked_reason", ""),
            "source": clean.get("source", "manual"),
        }
        blocked_since = now if values["status"] == "blocked" else None
        with self.connect() as db:
            cursor = db.execute(
                """
                INSERT INTO tasks (
                    title, description, course, assignee, due_at, importance,
                    status, progress, blocked_reason, blocked_since, source,
                    created_at, updated_at
                ) VALUES (
                    :title, :description, :course, :assignee, :due_at, :importance,
                    :status, :progress, :blocked_reason, :blocked_since, :source,
                    :created_at, :updated_at
                )
                """,
                {**values, "blocked_since": blocked_since, "created_at": now, "updated_at": now},
            )
            task_id = int(cursor.lastrowid)
        return self.get_task(task_id) or {}

    def update_task(self, task_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        clean = self._validate(payload, partial=True)
        existing = self.get_task(task_id)
        if not existing:
            return None
        if not clean:
            return existing
        now = iso_now()
        if clean.get("status") == "blocked" and not existing.get("blocked_since"):
            clean["blocked_since"] = now
        elif "status" in clean and clean["status"] != "blocked":
            clean["blocked_since"] = None
            if clean["status"] == "done":
                clean["progress"] = 100
        clean["updated_at"] = now
        assignments = ", ".join(f"{key} = :{key}" for key in clean)
        with self.connect() as db:
            db.execute(
                f"UPDATE tasks SET {assignments} WHERE id = :id",
                {**clean, "id": task_id},
            )
        return self.get_task(task_id)

    def check_in(self, task_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.get_task(task_id)
        if not existing:
            return None
        progress = int(payload.get("progress", existing["progress"]))
        status = payload.get("status", existing["status"])
        note = str(payload.get("note", "")).strip()
        blocked_reason = str(payload.get("blocked_reason", "")).strip()
        updated = self.update_task(
            task_id,
            {
                "progress": progress,
                "status": status,
                "blocked_reason": blocked_reason,
            },
        )
        with self.connect() as db:
            db.execute(
                "INSERT INTO checkins (task_id, progress, status, note, created_at) VALUES (?, ?, ?, ?, ?)",
                (task_id, progress, status, note, iso_now()),
            )
        return updated

    def seed_if_empty(self) -> bool:
        with self.connect() as db:
            count = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        if count:
            return False
        now = datetime.now(timezone.utc)
        samples = [
            {
                "title": "Chốt AI Spec và quality bar",
                "description": "Rà đủ 9 mục trước khi commit mốc cứng.",
                "course": "AI Thực Chiến",
                "assignee": "Vương",
                "due_at": (now - timedelta(days=1)).replace(hour=16, minute=59).isoformat(),
                "importance": "high",
                "status": "in_progress",
                "progress": 70,
                "source": "VLearn (mock)",
            },
            {
                "title": "Hoàn thiện 6 slide demo",
                "description": "Có một happy path và một case lỗi.",
                "course": "Mini Hackathon",
                "assignee": "Lan",
                "due_at": (now + timedelta(hours=5)).isoformat(),
                "importance": "high",
                "status": "in_progress",
                "progress": 35,
                "source": "Discord (mock)",
            },
            {
                "title": "Chạy đủ 20 case golden set",
                "description": "Không bỏ các case fail khỏi bảng kết quả.",
                "course": "Mini Hackathon",
                "assignee": "Minh",
                "due_at": (now + timedelta(days=1)).isoformat(),
                "importance": "medium",
                "status": "blocked",
                "progress": 25,
                "blocked_reason": "Chưa thống nhất định nghĩa pass/fail",
                "source": "manual",
            },
            {
                "title": "Tổng hợp feedback 5 người thử",
                "description": "Ghi quote nguyên văn và thay đổi sau test.",
                "course": "Mini Hackathon",
                "assignee": "An",
                "due_at": (now + timedelta(days=4)).isoformat(),
                "importance": "medium",
                "status": "todo",
                "progress": 0,
                "source": "manual",
            },
        ]
        for sample in samples:
            created = self.create_task(sample)
            if created["status"] == "blocked":
                three_days_ago = (now - timedelta(days=3)).isoformat()
                with self.connect() as db:
                    db.execute(
                        "UPDATE tasks SET blocked_since = ? WHERE id = ?",
                        (three_days_ago, created["id"]),
                    )
        return True
