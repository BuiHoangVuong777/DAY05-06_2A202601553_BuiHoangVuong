"""Agent tools: SSOT reads, RAG policy lookup, and two optional side-effects.

Every tool returns a plain dict/list so the results are JSON-serialisable and the
same functions can be handed to an LLM as function-calling tools (see TOOL_SPECS)
or called directly by the deterministic pipeline in agent.py.

Configuration (all env vars, no config file):
  SSOT_DB_PATH   path to the SQLite file            (default ./ssot/ssot.db)
  RAG_BASE_URL   rag-app backend base URL           (default http://localhost:8000)
  RAG_TIMEOUT    seconds                            (default 10)
  DUE_SOON_DAYS  horizon for get_due_soon_tasks     (default 3)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SSOT_DB_PATH = os.getenv("SSOT_DB_PATH", "./ssot/ssot.db")
RAG_BASE_URL = os.getenv("RAG_BASE_URL", "http://localhost:8000").rstrip("/")
RAG_TIMEOUT = float(os.getenv("RAG_TIMEOUT", "10"))
DUE_SOON_DAYS = int(os.getenv("DUE_SOON_DAYS", "3"))

# Real view names in the SSOT. The brief referred to v_tasks_week /
# v_tasks_priority; the schema actually defines these. Adapted rather than
# renamed, because the SSOT schema is read-only for this agent.
V_TODAY, V_WEEK = "v_tasks_today", "v_tasks_this_week"
V_OVERDUE, V_DUE_SOON = "v_tasks_overdue", "v_tasks_due_soon"
V_PRIORITY, V_BLOCKED = "v_task_priority", "v_tasks_blocked"


class SSOTUnavailable(RuntimeError):
    """Raised when the SQLite file is missing — surfaced, never silently faked."""


def _connect() -> sqlite3.Connection:
    path = Path(SSOT_DB_PATH)
    if not path.exists():
        raise SSOTUnavailable(
            f"SSOT database not found at {path.resolve()}. "
            "Set SSOT_DB_PATH, or export it from the container: "
            "docker compose -f ssot/docker-compose.yml cp ssot:/data/ssot.db ./ssot/ssot.db"
        )
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)   # read-only by default
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _rows(sql: str, args: tuple = ()) -> list[dict]:
    with _connect() as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def _task_view(view: str, limit: int) -> list[dict]:
    return _rows(f"SELECT * FROM {view} ORDER BY due_at LIMIT ?", (limit,))


# ---------------------------------------------------------------- SSOT reads

def get_tasks_today(limit: int = 50) -> list[dict]:
    """Tasks whose deadline falls on today's date and are not done."""
    return _task_view(V_TODAY, limit)


def get_tasks_week(limit: int = 200) -> list[dict]:
    """Tasks due in the current Monday–Sunday calendar week."""
    return _task_view(V_WEEK, limit)


def get_overdue_tasks(limit: int = 100) -> list[dict]:
    """Tasks past their deadline and not done."""
    return _task_view(V_OVERDUE, limit)


def get_due_soon_tasks(days: int | None = None, limit: int = 100) -> list[dict]:
    """Tasks due within the next `days` days (default DUE_SOON_DAYS), not yet overdue."""
    days = DUE_SOON_DAYS if days is None else days
    return _rows(
        f"""SELECT * FROM {V_PRIORITY}
             WHERE due_at IS NOT NULL
               AND due_at >= datetime('now')
               AND due_at <  datetime('now', ?)
             ORDER BY due_at LIMIT ?""",
        (f"+{int(days)} days", limit),
    )


def get_top_priority_tasks(limit: int = 10) -> list[dict]:
    """Open tasks with the SSOT's own score. agent.py re-ranks these with priority.py."""
    return _rows(f"SELECT * FROM {V_PRIORITY} ORDER BY priority_score DESC LIMIT ?", (limit,))


def get_blocked_tasks(limit: int = 100) -> list[dict]:
    return _rows(f"SELECT * FROM {V_BLOCKED} LIMIT ?", (limit,))


def get_upcoming_milestones(limit: int = 20) -> list[dict]:
    """Gates / demos / reviews from `schedules`. Never from RAG.

    Reads the base tables rather than v_upcoming_schedule: that view exposes
    team_name but not team_id, and the milestone rule needs the id to tell a
    team-scoped milestone from a programme-wide one.
    """
    return _rows(
        """SELECT s.id, s.title, s.event_type, s.starts_at, s.team_id,
                  tm.name AS team_name, s.project_id
             FROM schedules s
             LEFT JOIN teams tm ON tm.id = s.team_id
            WHERE s.event_type IN ('deadline', 'demo', 'review')
              AND s.starts_at >= datetime('now')
            ORDER BY s.starts_at LIMIT ?""",
        (limit,),
    )


def get_integrity_problems() -> list[dict]:
    """Rows here mean the SSOT itself is inconsistent. Expected: none."""
    return _rows("SELECT * FROM v_team_integrity")


# ------------------------------------------------------------------ RAG read

def search_policy(query: str, top_k: int = 3) -> dict:
    """Look up internal rules / strategy in the RAG corpus.

    Policy only. Never a source of task status, deadlines or assignees.
    Returns {ok, query, results[], error} — unreachable RAG degrades, never raises.
    """
    payload = json.dumps({"question": query, "top_k": top_k}).encode()
    req = urllib.request.Request(
        f"{RAG_BASE_URL}/api/query", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=RAG_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "query": query, "results": [],
                "error": f"RAG unavailable at {RAG_BASE_URL}: {type(exc).__name__}"}

    return {
        "ok": True, "query": query, "error": None,
        "mode": data.get("mode"),
        "results": [
            {"title": s.get("title"), "score": s.get("score"),
             "ref": f"{s.get('source_file', '')}{s.get('source_pointer', '')}"}
            for s in data.get("sources", [])
        ],
    }


# ------------------------------------------------------------- side effects

def update_task_status(task_id: int, status: str, note: str = "", dry_run: bool = True) -> dict:
    """Write a task's status back to the SSOT. dry_run=True by default.

    The agent pipeline never calls this on its own — status changes are a human
    decision. Exposed so a UI or an LLM can invoke it deliberately.
    """
    allowed = {"todo", "doing", "blocked", "done"}
    if status not in allowed:
        return {"ok": False, "error": f"status must be one of {sorted(allowed)}"}
    if dry_run:
        return {"ok": True, "dry_run": True, "task_id": task_id, "status": status,
                "note": note, "detail": "no write performed (dry_run=True)"}

    path = Path(SSOT_DB_PATH)
    if not path.exists():
        return {"ok": False, "error": f"SSOT not found at {path}"}
    con = sqlite3.connect(path)          # read-write connection, only here
    try:
        con.execute("PRAGMA foreign_keys = ON")
        cur = con.execute(
            "UPDATE tasks SET status = ?, description = CASE WHEN ? <> '' "
            "THEN TRIM(description || char(10) || ?) ELSE description END WHERE id = ?",
            (status, note, note, task_id),
        )
        con.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": f"no task with id {task_id}"}
        return {"ok": True, "dry_run": False, "task_id": task_id, "status": status, "note": note}
    except sqlite3.Error as exc:
        con.rollback()
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        con.close()


def send_notification(payload: dict, dry_run: bool = True) -> dict:
    """Stub notification sink. Prints in dry-run; wire to Discord/Slack here."""
    if dry_run:
        return {"ok": True, "dry_run": True, "channel": payload.get("channel", "stdout"),
                "preview": payload.get("text", "")[:280]}
    return {"ok": False, "error": "no notification channel configured; "
                                  "implement send_notification(dry_run=False)"}


# ------------------------------------------------ registry for LLM tool-calling

TOOLS = {
    "get_tasks_today": get_tasks_today,
    "get_tasks_week": get_tasks_week,
    "get_overdue_tasks": get_overdue_tasks,
    "get_due_soon_tasks": get_due_soon_tasks,
    "get_top_priority_tasks": get_top_priority_tasks,
    "search_policy": search_policy,
    "update_task_status": update_task_status,
    "send_notification": send_notification,
}

# OpenAI/Anthropic-style schemas, so the same tools can be handed to an LLM.
TOOL_SPECS = [
    {"name": "get_tasks_today", "description": "Tasks due today (SSOT).",
     "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    {"name": "get_tasks_week", "description": "Tasks due this calendar week (SSOT).",
     "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    {"name": "get_overdue_tasks", "description": "Tasks past deadline (SSOT).",
     "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    {"name": "get_due_soon_tasks", "description": "Tasks due within N days (SSOT).",
     "parameters": {"type": "object", "properties": {"days": {"type": "integer"},
                                                     "limit": {"type": "integer"}}}},
    {"name": "get_top_priority_tasks", "description": "Top-priority open tasks with reasons.",
     "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    {"name": "search_policy",
     "description": "Search internal rules/strategy docs. Policy only — never task data.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"},
                                                     "top_k": {"type": "integer"}},
                    "required": ["query"]}},
    {"name": "update_task_status", "description": "Write a task status back to the SSOT.",
     "parameters": {"type": "object",
                    "properties": {"task_id": {"type": "integer"},
                                   "status": {"type": "string",
                                              "enum": ["todo", "doing", "blocked", "done"]},
                                   "note": {"type": "string"},
                                   "dry_run": {"type": "boolean"}},
                    "required": ["task_id", "status"]}},
    {"name": "send_notification", "description": "Send a notification (stub).",
     "parameters": {"type": "object", "properties": {"payload": {"type": "object"},
                                                     "dry_run": {"type": "boolean"}},
                    "required": ["payload"]}},
]


def call_tool(name: str, **kwargs) -> Any:
    """Dispatch by name — the entry point an LLM tool-call loop would use."""
    if name not in TOOLS:
        return {"ok": False, "error": f"unknown tool '{name}'. Available: {sorted(TOOLS)}"}
    try:
        return TOOLS[name](**kwargs)
    except SSOTUnavailable as exc:
        return {"ok": False, "error": str(exc)}
    except TypeError as exc:
        return {"ok": False, "error": f"bad arguments for {name}: {exc}"}
