"""Deterministic priority rule engine.

No LLM touches this. Each rule is a named function that looks at one task (plus
the upcoming-milestone list) and returns (points, reason_fragment). The score is
the sum; the reason is the fragments joined. Same input always gives the same
output, which is what makes the agent's ranking explainable and testable.

To change how the agent prioritises, edit RULES below — nothing else.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Callable, Iterable

# --- tunables -------------------------------------------------------------
DUE_SOON_DAYS = 3          # "due soon" horizon
BLOCKED_LONG_DAYS = 2      # blocked at least this long counts as stuck
NICE_TO_HAVE_PRIORITY = 1  # tasks at this DB priority sink to the bottom
MILESTONE_HORIZON_DAYS = 7 # only boost against milestones inside this window

Rule = Callable[[dict, dt.datetime, list[dict]], tuple[float, str]]


def utc_now() -> dt.datetime:
    """Naive UTC — the clock the SSOT uses.

    The SSOT stores timestamps from SQLite's datetime('now'), which is UTC, and
    its views filter with the same function. Scoring with a local clock instead
    silently shifts every window by the host's offset: on a UTC+7 host the views
    return "due today (UTC)" rows that a local-clock check then rejects as
    off-date. Always compare UTC to UTC.
    """
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _due(task: dict) -> dt.datetime | None:
    raw = task.get("due_at")
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(str(raw).replace("Z", ""))
    except ValueError:
        return None


def _hours(a: dt.datetime, b: dt.datetime) -> float:
    return (a - b).total_seconds() / 3600.0


# --- rules ----------------------------------------------------------------
# Ordered by intent: hard deadlines dominate, then blockers, then milestones,
# then importance, then the nice-to-have demotion.

def rule_overdue(task, now, milestones):
    """Hard deadlines first: overdue outranks everything else."""
    due = _due(task)
    if due is None or due >= now:
        return 0.0, ""
    over = _hours(now, due)
    days = over / 24
    label = f"quá hạn {over:.0f} giờ" if over < 24 else f"quá hạn {days:.1f} ngày"
    return 1000.0 + min(over, 500.0), label


def rule_due_today(task, now, milestones):
    due = _due(task)
    if due is None or due < now or due.date() != now.date():
        return 0.0, ""
    return 400.0, "đến hạn hôm nay"


def rule_due_soon(task, now, milestones):
    """Earlier alerts the closer the deadline is (excludes today, scored above)."""
    due = _due(task)
    if due is None or due < now or due.date() == now.date():
        return 0.0, ""
    hours = _hours(due, now)
    if hours > DUE_SOON_DAYS * 24:
        return 0.0, ""
    return max(0.0, 200.0 - hours), f"đến hạn trong {hours / 24:.1f} ngày"


def rule_blocked(task, now, milestones):
    """Blocked tasks rank higher; long-blocked rank higher still."""
    if task.get("status") != "blocked":
        return 0.0, ""
    since_raw = task.get("blocked_since")
    since = None
    if since_raw:
        try:
            since = dt.datetime.fromisoformat(str(since_raw).replace("Z", ""))
        except ValueError:
            since = None
    if since is None:
        return 50.0, "đang bị kẹt"
    days = (now - since).total_seconds() / 86400
    if days >= BLOCKED_LONG_DAYS:
        return 150.0, f"kẹt {days:.1f} ngày"
    return 50.0, "đang bị kẹt"


def rule_milestone_impact(task, now, milestones):
    """Boost tasks due before the next gate/demo/review that covers their team.

    `milestones` comes from the schedules table, never from RAG.
    """
    due = _due(task)
    if due is None or not milestones:
        return 0.0, ""
    horizon = now + dt.timedelta(days=MILESTONE_HORIZON_DAYS)
    for ms in milestones:
        starts = ms.get("_starts")
        if starts is None or starts > horizon:
            continue
        scoped = ms.get("team_id") in (None, task.get("team_id"))
        if scoped and due <= starts:
            return 120.0, f"ảnh hưởng mốc “{ms.get('title')}”"
    return 0.0, ""


def rule_importance(task, now, milestones):
    p = int(task.get("priority") or 3)
    return p * 20.0, f"mức quan trọng {p}/5"


def rule_nice_to_have(task, now, milestones):
    """Lowest-importance work sinks to the bottom."""
    if int(task.get("priority") or 3) == NICE_TO_HAVE_PRIORITY:
        return -100.0, "nice-to-have"
    return 0.0, ""


RULES: list[tuple[str, Rule]] = [
    ("overdue", rule_overdue),
    ("due_today", rule_due_today),
    ("due_soon", rule_due_soon),
    ("blocked", rule_blocked),
    ("milestone_impact", rule_milestone_impact),
    ("importance", rule_importance),
    ("nice_to_have", rule_nice_to_have),
]

# Documented gap: the SSOT has no task-dependency table, so "tasks that block
# other tasks" cannot be computed. Adding it would require a schema change,
# which is out of scope. See README → Known limitations.
UNIMPLEMENTABLE = {
    "blocks_other_tasks": "SSOT has no task-dependency table; cannot be derived without a schema change."
}


def score_task(task: dict, now: dt.datetime, milestones: list[dict] | None = None) -> dict:
    """Return the task annotated with agent_score / agent_reason / agent_rules."""
    milestones = milestones or []
    total, fragments, fired = 0.0, [], []
    for name, rule in RULES:
        points, fragment = rule(task, now, milestones)
        if points or fragment:
            total += points
            fired.append(name)
            if fragment:
                fragments.append(fragment)
    out = dict(task)
    out["agent_score"] = round(total, 1)
    out["agent_reason"] = " · ".join(fragments) if fragments else "không có tín hiệu ưu tiên"
    out["agent_rules"] = fired
    return out


def rank(tasks: Iterable[dict], now: dt.datetime, milestones: list[dict] | None = None) -> list[dict]:
    """Score every task and sort by score desc, then by deadline as a stable tie-break."""
    now = now or utc_now()
    scored = [score_task(t, now, milestones) for t in tasks]
    scored.sort(key=lambda t: (-t["agent_score"], str(t.get("due_at") or "9999"), t.get("id", 0)))
    return scored
