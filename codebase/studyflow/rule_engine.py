"""Transparent prioritisation and reminder rules.

The rules are deliberately deterministic so the team can explain every ranking
decision during the hackathon demo. AI is used separately for task extraction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


ACTIVE_STATUSES = {"todo", "in_progress", "blocked"}


def parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def priority_for(task: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Return a score plus human-readable reasons for one task."""
    current = parse_datetime(now) or utc_now()
    status = task.get("status", "todo")
    if status == "done":
        return {
            "score": -1,
            "level": "done",
            "reasons": ["Đã hoàn thành"],
            "recommendation": "Không cần nhắc lại.",
        }

    score = 0
    reasons: list[str] = []
    recommendation = "Tiếp tục theo kế hoạch và check-in khi có thay đổi."
    due = parse_datetime(task.get("due_at"))
    if due:
        seconds = (due - current).total_seconds()
        days = seconds / 86_400
        if seconds < 0:
            overdue_days = max(1, int(abs(days)) + 1)
            score += 100 + min(overdue_days * 5, 30)
            reasons.append(f"Quá hạn {overdue_days} ngày")
            recommendation = "Chốt lại deadline và bước nhỏ tiếp theo ngay hôm nay."
        elif due.date() == current.date():
            score += 60
            reasons.append("Đến hạn hôm nay")
            recommendation = "Dành block thời gian gần nhất để hoàn thành hoặc báo blocker."
        elif days <= 3:
            score += 35
            reasons.append("Deadline trong 3 ngày")
        elif days <= 7:
            score += 15
            reasons.append("Deadline trong tuần")

    importance = task.get("importance", "medium")
    importance_score = {"high": 30, "medium": 15, "low": 5}.get(importance, 15)
    score += importance_score
    if importance == "high":
        reasons.append("Độ quan trọng cao")

    blocked_since = parse_datetime(task.get("blocked_since"))
    if status == "blocked" or blocked_since:
        stuck_days = max(0, int((current - (blocked_since or current)).total_seconds() / 86_400))
        score += 20 + min(stuck_days * 10, 40)
        reasons.append(f"Đang kẹt {stuck_days} ngày" if stuck_days else "Đang bị kẹt")
        if stuck_days >= 2:
            recommendation = (
                "Chia task thành bước ≤30 phút hoặc thêm/đổi người phụ trách sau khi team xác nhận."
            )
        else:
            recommendation = "Nêu blocker cụ thể để team hỗ trợ trong check-in kế tiếp."

    progress = int(task.get("progress") or 0)
    if due and 0 <= (due - current).total_seconds() <= 7 * 86_400 and progress < 50:
        score += 20
        reasons.append("Tiến độ dưới 50% gần deadline")

    if score >= 100:
        level = "critical"
    elif score >= 60:
        level = "high"
    elif score >= 35:
        level = "medium"
    else:
        level = "low"
    return {
        "score": score,
        "level": level,
        "reasons": reasons or ["Chưa có tín hiệu khẩn cấp"],
        "recommendation": recommendation,
    }


def enrich_and_rank(
    tasks: list[dict[str, Any]], now: datetime | None = None
) -> list[dict[str, Any]]:
    enriched = []
    for task in tasks:
        item = dict(task)
        item["priority"] = priority_for(item, now)
        enriched.append(item)
    return sorted(
        enriched,
        key=lambda item: (
            item["status"] == "done",
            -item["priority"]["score"],
            item.get("due_at") or "9999",
        ),
    )


def build_dashboard(
    tasks: list[dict[str, Any]], now: datetime | None = None
) -> dict[str, Any]:
    current = parse_datetime(now) or utc_now()
    ranked = enrich_and_rank(tasks, current)
    active = [item for item in ranked if item.get("status") in ACTIVE_STATUSES]
    done = [item for item in ranked if item.get("status") == "done"]

    today = []
    alerts = []
    for task in active:
        due = parse_datetime(task.get("due_at"))
        if due and due.date() <= current.date():
            today.append(task)
        if task["priority"]["level"] == "critical" or any(
            reason.startswith("Đang kẹt") for reason in task["priority"]["reasons"]
        ):
            alerts.append(task)

    completion = round(100 * len(done) / len(ranked)) if ranked else 0
    weekly_unfinished = [
        item
        for item in active
        if not parse_datetime(item.get("due_at"))
        or (parse_datetime(item["due_at"]) - current).total_seconds() <= 7 * 86_400
    ]

    reminder_lines = []
    for task in active[:5]:
        primary_reason = task["priority"]["reasons"][0]
        reminder_lines.append(
            f"• {task['title']} — {primary_reason} · {task.get('assignee') or 'Chưa giao'}"
        )

    return {
        "generated_at": current.isoformat(),
        "summary": {
            "active": len(active),
            "due_today_or_overdue": len(today),
            "stuck_or_critical": len(alerts),
            "completion_percent": completion,
        },
        "today": today,
        "weekly_unfinished": weekly_unfinished,
        "alerts": alerts,
        "ranked_tasks": ranked,
        "discord_preview": {
            "is_mock": True,
            "channel": "#team-study",
            "message": "📌 Việc cần ưu tiên\n"
            + ("\n".join(reminder_lines) if reminder_lines else "Không còn task đang mở. Tuyệt vời!"),
        },
    }
