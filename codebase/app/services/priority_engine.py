"""RULE ENGINE thuần Python — KHÔNG gọi LLM, KHÔNG cần DB/mạng để test.

Nhận vào bất kỳ object nào có các thuộc tính: due_date, importance, status,
blocked_since (có thể None). Gắn priority_score/priority_reason lên chính
object đó (mutate) + gắn thêm .flags (dict, không lưu DB, chỉ để UI hiển thị
cờ cảnh báo), rồi trả về list đã sắp xếp giảm dần theo priority_score.

Quy tắc chấm điểm (càng cao càng ưu tiên):
  - Task 'done' luôn rớt xuống đáy.
  - Quá hạn -> điểm rất cao, càng quá hạn lâu điểm càng cao (cộng thêm, có trần).
  - Chưa quá hạn -> càng gần deadline điểm càng cao.
  - importance (1-5) cộng thêm điểm tuyến tính.
  - blocked liên tục >= BLOCKED_DAYS_THRESHOLD ngày -> cộng điểm mạnh + gắn cờ blocked_long.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Iterable

from app.config import BLOCKED_DAYS_THRESHOLD, DUE_SOON_DAYS

DONE_SCORE = -1000.0
OVERDUE_BASE = 1000.0
OVERDUE_HOURS_CAP = 500.0
NOT_OVERDUE_WINDOW_HOURS = 200.0
IMPORTANCE_WEIGHT = 10.0
BLOCKED_LONG_BONUS = 50.0


def score_task(task: Any, today: dt.datetime) -> tuple[float, str, dict]:
    """Trả về (priority_score, priority_reason, flags) cho một task."""
    reasons: list[str] = []
    flags = {"overdue": False, "due_soon": False, "blocked_long": False}

    if task.status == "done":
        return DONE_SCORE, "Đã hoàn thành", flags

    hours_until_due = (task.due_date - today).total_seconds() / 3600
    score = 0.0

    if hours_until_due < 0:
        overdue_hours = -hours_until_due
        flags["overdue"] = True
        score += OVERDUE_BASE + min(overdue_hours, OVERDUE_HOURS_CAP)
        if overdue_hours < 24:
            reasons.append(f"Quá hạn {overdue_hours:.0f} giờ")
        else:
            reasons.append(f"Quá hạn {overdue_hours / 24:.1f} ngày")
    else:
        score += max(0.0, NOT_OVERDUE_WINDOW_HOURS - hours_until_due)
        if hours_until_due <= DUE_SOON_DAYS * 24:
            flags["due_soon"] = True
            reasons.append(f"Sắp đến hạn (còn {hours_until_due:.0f} giờ)")

    importance_points = task.importance * IMPORTANCE_WEIGHT
    score += importance_points
    reasons.append(f"Mức quan trọng {task.importance}/5")

    if task.status == "blocked" and task.blocked_since is not None:
        blocked_days = (today - task.blocked_since).total_seconds() / 86400
        if blocked_days >= BLOCKED_DAYS_THRESHOLD:
            flags["blocked_long"] = True
            score += BLOCKED_LONG_BONUS
            reasons.append(f"Đang kẹt {blocked_days:.1f} ngày liên tục")

    return score, " · ".join(reasons), flags


def rank_tasks(tasks: Iterable[Any], today: dt.datetime | None = None) -> list[Any]:
    """Chấm điểm + gắn cờ cho toàn bộ task, trả về list đã sắp xếp giảm dần theo priority_score."""
    today = today or dt.datetime.now()
    scored = list(tasks)
    for task in scored:
        score, reason, flags = score_task(task, today)
        task.priority_score = score
        task.priority_reason = reason
        task.flags = flags
    scored.sort(key=lambda t: t.priority_score, reverse=True)
    return scored
