"""Connector MÔ PHỎNG cho VLearn: đọc file JSON mock và tạo Task source='vlearn'.

Đây không phải tích hợp API VLearn thật — chỉ đọc file tĩnh trong data/vlearn_deadlines.json
để mô phỏng việc đồng bộ deadline. due_offset_hours được cộng vào thời điểm import để
deadline mẫu luôn có cái quá hạn / sắp tới bất kể demo chạy vào lúc nào.
"""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import select

from app.config import VLEARN_MOCK_PATH
from app.database import get_session
from app.models import Task


def import_vlearn_deadlines() -> dict:
    """Import deadline mẫu từ file mock. Idempotent theo title (import nhiều lần không tạo trùng)."""
    if not VLEARN_MOCK_PATH.exists():
        return {"created": 0, "skipped": 0, "error": f"Không tìm thấy file mock: {VLEARN_MOCK_PATH}"}

    try:
        items = json.loads(VLEARN_MOCK_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"created": 0, "skipped": 0, "error": f"Lỗi đọc file mock: {exc}"}

    now = dt.datetime.now()
    created = 0
    skipped = 0

    with get_session() as session:
        existing_titles = set(
            session.execute(select(Task.title).where(Task.source == "vlearn")).scalars().all()
        )
        for item in items:
            title = item.get("title", "").strip()
            if not title or title in existing_titles:
                skipped += 1
                continue

            due_date = now + dt.timedelta(hours=item.get("due_offset_hours", 0))
            task = Task(
                title=title,
                description=item.get("description", ""),
                due_date=due_date,
                importance=int(item.get("importance", 3)),
                status="todo",
                assignee="",
                source="vlearn",
            )
            session.add(task)
            existing_titles.add(title)
            created += 1

        session.commit()

    return {"created": created, "skipped": skipped}
