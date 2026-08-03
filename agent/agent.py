"""Progress-management agent: SSOT + RAG -> fixed JSON.

The loop is deterministic on purpose:

    mode (+ optional query)
      -> read tasks via tools      (SSOT is the only source of task facts)
      -> read policy via RAG       (rules/strategy only, never task facts)
      -> score with priority.RULES (pure function, no LLM)
      -> assemble the fixed 7-key JSON

Output keys are always exactly:
  today_items, week_items, overdue_alerts, due_soon_alerts,
  priority_suggestions, actions, sources_used

The schema is fixed, so anything that would otherwise be an extra key rides
inside it: missing data and clarification requests appear in `actions` with
type="clarification_needed"; source availability appears in `sources_used`.

CLI:
    python -m agent.agent --mode daily
    python -m agent.agent --mode weekly --query "quy định nộp báo cáo tuần"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from typing import Any

try:                       # works as `python -m agent.agent` and as `python agent.py`
    from agent import priority, tools
except ImportError:        # pragma: no cover
    import priority, tools  # type: ignore

OUTPUT_KEYS = ["today_items", "week_items", "overdue_alerts", "due_soon_alerts",
               "priority_suggestions", "actions", "sources_used"]

# Policy questions the agent asks RAG per mode. Rules/strategy only.
POLICY_QUERIES = {
    "daily":  ["Quy định nộp daily report và stand-up"],
    "weekly": ["Quy định nộp báo cáo tuần và weekly report",
               "Gate là gì và dùng để làm gì"],
}


def _item(task: dict, reason: str | None = None) -> dict:
    """Project a task row onto the fixed item shape. Values are copied, never inferred."""
    return {
        "task_id": task.get("id"),
        "title": task.get("title"),
        "deadline": task.get("due_at"),
        "status": task.get("status"),
        "priority": task.get("priority"),
        "reason": reason if reason is not None else task.get("agent_reason", ""),
        # extras beyond the required six — useful and still concise
        "project_id": task.get("project_id"),
        "team": task.get("team_name"),
        "assignee": task.get("assignee_name"),
        "score": task.get("agent_score"),
    }


def _parse(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(str(ts).replace("Z", ""))
    except ValueError:
        return None


def _bottlenecks(blocked: list[dict], now: dt.datetime) -> list[dict]:
    """Group blocked tasks by their blocker string — the weekly bottleneck view."""
    groups: dict[str, list[dict]] = {}
    for t in blocked:
        groups.setdefault(t.get("blocked_reason") or "(không ghi lý do)", []).append(t)

    out = []
    for reason, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        oldest = min((_parse(t.get("blocked_since")) for t in items
                      if _parse(t.get("blocked_since"))), default=None)
        days = round((now - oldest).total_seconds() / 86400, 1) if oldest else None
        teams = sorted({t.get("team_name") for t in items if t.get("team_name")})
        out.append({
            "kind": "bottleneck",
            "blocker": reason,
            "task_count": len(items),
            "teams_affected": teams,
            "oldest_blocked_since": oldest.isoformat(sep=" ") if oldest else None,
            "blocked_days": days,
            "task_ids": [t.get("id") for t in items][:10],
            "reason": (f"{len(items)} task bị chặn bởi cùng một nguyên nhân"
                       + (f", lâu nhất {days} ngày" if days else "")
                       + (f", ảnh hưởng {len(teams)} team" if len(teams) > 1 else "")),
        })
    return out


def run(mode: str = "daily", query: str | None = None,
        top_n: int = 10, now: dt.datetime | None = None) -> dict:
    """Run one pass. Always returns the fixed 7-key dict, even on failure."""
    now = now or priority.utc_now()   # SSOT is UTC; never mix clocks
    result: dict[str, list] = {k: [] for k in OUTPUT_KEYS}

    if mode not in ("daily", "weekly"):
        result["actions"].append({
            "type": "clarification_needed", "field": "mode",
            "detail": f"unknown mode {mode!r}; expected 'daily' or 'weekly'",
        })
        return result

    # --- 1. SSOT reads ----------------------------------------------------
    try:
        overdue = tools.get_overdue_tasks()
        today = tools.get_tasks_today()
        due_soon = tools.get_due_soon_tasks()
        blocked = tools.get_blocked_tasks()
        milestones = tools.get_upcoming_milestones()
        week = tools.get_tasks_week() if mode == "weekly" else []
        integrity = tools.get_integrity_problems()
    except tools.SSOTUnavailable as exc:
        # Missing data is stated, never guessed around.
        result["sources_used"].append({"type": "ssot", "ref": tools.SSOT_DB_PATH,
                                       "status": "unavailable", "detail": str(exc)})
        result["actions"].append({"type": "clarification_needed", "field": "ssot_db",
                                  "detail": str(exc)})
        return result

    result["sources_used"].append({
        "type": "ssot", "ref": tools.SSOT_DB_PATH, "status": "ok",
        "detail": (f"overdue={len(overdue)} today={len(today)} due_soon={len(due_soon)} "
                   f"blocked={len(blocked)} week={len(week)}"),
        "reference_time": now.isoformat(sep=" ", timespec="seconds"),
    })

    for ms in milestones:                      # pre-parse once for the rule engine
        ms["_starts"] = _parse(ms.get("starts_at"))

    # --- 2. deterministic scoring ----------------------------------------
    rank = lambda rows: priority.rank(rows, now, milestones)  # noqa: E731
    overdue_r, today_r, soon_r = rank(overdue), rank(today), rank(due_soon)
    week_r = rank(week) if week else []

    result["overdue_alerts"] = [_item(t) for t in overdue_r[:top_n]]
    result["today_items"] = [_item(t) for t in today_r[:top_n]]
    result["due_soon_alerts"] = [_item(t) for t in soon_r[:top_n]]
    if mode == "weekly":
        result["week_items"] = [_item(t) for t in week_r[:50]]

    # --- 3. priority suggestions -----------------------------------------
    # Ranked union of everything urgent, deduped by task id, highest score first.
    pool: dict[Any, dict] = {}
    for t in overdue_r + today_r + soon_r + rank(blocked):
        pool.setdefault(t.get("id"), t)
    ranked = sorted(pool.values(), key=lambda t: -t["agent_score"])

    result["priority_suggestions"] = [
        {**_item(t), "kind": "task", "rules_fired": t.get("agent_rules", [])}
        for t in ranked[:top_n]
    ]

    if mode == "weekly":
        # Weekly adds bottlenecks and milestone impact on top of the task list.
        result["priority_suggestions"].extend(_bottlenecks(blocked, now))
        for ms in milestones:
            starts = ms.get("_starts")
            if not starts:
                continue
            days = round((starts - now).total_seconds() / 86400, 1)
            at_risk = [t for t in ranked
                       if (_parse(t.get("due_at")) or now) <= starts
                       and t.get("status") != "done"]
            result["priority_suggestions"].append({
                "kind": "milestone_impact",
                "milestone": ms.get("title"),
                "event_type": ms.get("event_type"),
                "starts_at": ms.get("starts_at"),
                "team": ms.get("team_name") or "(all teams)",
                "days_until": days,
                "open_tasks_due_before": len(at_risk),
                "reason": f"{len(at_risk)} task chưa xong đến hạn trước mốc này ({days} ngày nữa)",
            })

    # --- 4. RAG policy lookup (rules/strategy only) -----------------------
    queries = list(POLICY_QUERIES.get(mode, []))
    if query:
        queries.append(query)
    for q in queries:
        hit = tools.search_policy(q)
        if hit["ok"]:
            for r in hit["results"]:
                result["sources_used"].append({
                    "type": "rag_policy", "ref": r["ref"], "status": "ok",
                    "detail": f"{r['title']} (score {r['score']}) for query: {q}",
                })
        else:
            result["sources_used"].append({"type": "rag_policy", "ref": tools.RAG_BASE_URL,
                                           "status": "unavailable", "detail": hit["error"]})
            result["actions"].append({
                "type": "clarification_needed", "field": "rag_policy",
                "detail": f"Could not reach the policy corpus ({hit['error']}). "
                          "Priority ranking is unaffected — it is computed from the SSOT — "
                          "but policy citations are missing from this report.",
            })

    # --- 5. actions -------------------------------------------------------
    if integrity:
        result["actions"].append({
            "type": "data_integrity", "severity": "high",
            "detail": f"{len(integrity)} team(s) fail v_team_integrity",
            "rows": integrity[:5],
        })

    headline = result["priority_suggestions"][0] if result["priority_suggestions"] else None
    if headline:
        text = (f"[{mode}] {len(overdue_r)} quá hạn · {len(today_r)} đến hạn hôm nay · "
                f"{len(soon_r)} sắp đến hạn. Ưu tiên số 1: "
                f"{headline.get('title') or headline.get('blocker')} — {headline.get('reason')}")
        result["actions"].append({
            "type": "notification",
            **tools.send_notification({"channel": "stdout", "text": text}, dry_run=True),
        })

    result["actions"].append({
        "type": "note", "field": "update_task_status",
        "detail": "Not called. Status changes are a human decision; invoke the tool "
                  "explicitly with dry_run=False.",
    })
    if priority.UNIMPLEMENTABLE:
        result["actions"].append({
            "type": "known_limitation",
            "detail": "; ".join(f"{k}: {v}" for k, v in priority.UNIMPLEMENTABLE.items()),
        })
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Progress-management agent (SSOT + RAG).")
    ap.add_argument("--mode", choices=["daily", "weekly"], default="daily")
    ap.add_argument("--query", help="optional extra policy question for RAG")
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--db", help="override SSOT_DB_PATH")
    ap.add_argument("--rag", help="override RAG_BASE_URL")
    args = ap.parse_args(argv)

    if args.db:
        tools.SSOT_DB_PATH = args.db
    if args.rag:
        tools.RAG_BASE_URL = args.rag.rstrip("/")

    out = run(mode=args.mode, query=args.query, top_n=args.top_n)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()
    # Non-zero when the SSOT could not be read, so a scheduler notices.
    return 1 if any(s.get("type") == "ssot" and s.get("status") != "ok"
                    for s in out["sources_used"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
