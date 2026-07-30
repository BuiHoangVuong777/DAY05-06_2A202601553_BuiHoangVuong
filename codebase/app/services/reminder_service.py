"""Hàm THUẦN: given danh sách task + ngày hôm nay -> việc cần nhắc + task kẹt cần cảnh báo.

Không dùng scheduler thật — trang UI gọi hàm này ngay khi bấm nút.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Iterable

from app.config import BLOCKED_DAYS_THRESHOLD


def get_today_reminders(tasks: Iterable[Any], today: dt.datetime | None = None) -> dict:
    """Trả về {"due_today": [...], "blocked_alerts": [...]} đã sắp xếp mức khẩn cấp giảm dần.

    - due_today: task chưa xong, quá hạn hoặc hạn rơi đúng hôm nay.
    - blocked_alerts: task đang blocked liên tục >= BLOCKED_DAYS_THRESHOLD ngày.
    """
    today = today or dt.datetime.now()
    due_today: list[Any] = []
    blocked_alerts: list[Any] = []

    for task in tasks:
        if task.status == "done":
            continue

        is_overdue = task.due_date < today
        is_due_today = task.due_date.date() == today.date()
        if is_overdue or is_due_today:
            due_today.append(task)

        if task.status == "blocked" and task.blocked_since is not None:
            blocked_days = (today - task.blocked_since).total_seconds() / 86400
            if blocked_days >= BLOCKED_DAYS_THRESHOLD:
                blocked_alerts.append(task)

    due_today.sort(key=lambda t: t.due_date)
    blocked_alerts.sort(key=lambda t: t.blocked_since)

    return {"due_today": due_today, "blocked_alerts": blocked_alerts}
