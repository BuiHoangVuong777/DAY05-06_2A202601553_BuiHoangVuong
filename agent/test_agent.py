"""Tests: priority rules, output schema, and the degraded paths.

Run:  python3 -m pytest agent/test_agent.py -q
      (or plain `python3 agent/test_agent.py` — it self-runs without pytest)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent import agent, priority, tools  # noqa: E402

NOW = dt.datetime(2026, 7, 30, 12, 0, 0)


def _task(**kw):
    base = {"id": 1, "title": "t", "status": "todo", "priority": 3,
            "due_at": None, "blocked_since": None, "team_id": 1}
    base.update(kw)
    return base


# ------------------------------------------------------------ priority rules
def test_overdue_outranks_everything():
    overdue = priority.score_task(_task(id=1, due_at="2026-07-28 12:00:00"), NOW)
    today = priority.score_task(_task(id=2, due_at="2026-07-30 23:00:00"), NOW)
    top5 = priority.score_task(_task(id=3, priority=5, due_at="2026-08-20 12:00:00"), NOW)
    assert overdue["agent_score"] > today["agent_score"] > top5["agent_score"]
    assert "quá hạn" in overdue["agent_reason"]


def test_blocked_long_beats_blocked_briefly():
    long_ = priority.score_task(_task(status="blocked", blocked_since="2026-07-25 12:00:00"), NOW)
    brief = priority.score_task(_task(status="blocked", blocked_since="2026-07-30 06:00:00"), NOW)
    assert long_["agent_score"] > brief["agent_score"]
    assert "kẹt" in long_["agent_reason"]


def test_milestone_boost_applies_only_within_scope():
    ms = [{"title": "Gate 2", "team_id": 1, "_starts": dt.datetime(2026, 8, 2, 12, 0)}]
    in_scope = priority.score_task(_task(team_id=1, due_at="2026-08-01 12:00:00"), NOW, ms)
    other_team = priority.score_task(_task(team_id=2, due_at="2026-08-01 12:00:00"), NOW, ms)
    assert in_scope["agent_score"] > other_team["agent_score"]
    assert "ảnh hưởng mốc" in in_scope["agent_reason"]


def test_nice_to_have_sinks():
    nice = priority.score_task(_task(priority=1), NOW)
    normal = priority.score_task(_task(priority=3), NOW)
    assert nice["agent_score"] < normal["agent_score"]
    assert "nice-to-have" in nice["agent_reason"]


def test_scoring_is_deterministic():
    t = _task(due_at="2026-07-28 12:00:00", status="blocked", blocked_since="2026-07-26 12:00:00")
    a = priority.score_task(t, NOW)
    b = priority.score_task(t, NOW)
    assert a["agent_score"] == b["agent_score"] and a["agent_reason"] == b["agent_reason"]


def test_rank_orders_descending():
    rows = [_task(id=1, priority=1), _task(id=2, due_at="2026-07-20 12:00:00"), _task(id=3, priority=5)]
    ranked = priority.rank(rows, NOW)
    assert [r["id"] for r in ranked] == [2, 3, 1]


# ----------------------------------------------------------- output contract
EXPECTED_KEYS = ["today_items", "week_items", "overdue_alerts", "due_soon_alerts",
                 "priority_suggestions", "actions", "sources_used"]


def _run(mode="daily", **kw):
    return agent.run(mode=mode, **kw)


def test_schema_keys_exact_daily():
    assert list(_run("daily").keys()) == EXPECTED_KEYS


def test_schema_keys_exact_weekly():
    assert list(_run("weekly").keys()) == EXPECTED_KEYS


def test_output_is_json_serialisable():
    json.dumps(_run("weekly"), ensure_ascii=False)


def test_daily_omits_week_items():
    assert _run("daily")["week_items"] == []


def test_weekly_includes_week_items_and_bottlenecks():
    out = _run("weekly")
    assert out["week_items"], "weekly must populate week_items"
    kinds = {p.get("kind") for p in out["priority_suggestions"]}
    assert "bottleneck" in kinds and "milestone_impact" in kinds


def test_items_carry_required_fields():
    out = _run("daily")
    required = {"task_id", "title", "deadline", "status", "priority", "reason"}
    for key in ("today_items", "overdue_alerts", "due_soon_alerts"):
        for item in out[key]:
            assert required <= set(item), f"{key} item missing fields"
            assert item["reason"], "every item needs a reason"


def test_invalid_mode_is_reported_not_guessed():
    out = _run("monthly")
    assert list(out.keys()) == EXPECTED_KEYS
    assert any(a["type"] == "clarification_needed" for a in out["actions"])


# ------------------------------------------------------------ degraded paths
def test_missing_ssot_states_the_problem(monkeypatch=None):
    old = tools.SSOT_DB_PATH
    tools.SSOT_DB_PATH = "/nonexistent/nope.db"
    try:
        out = _run("daily")
        assert list(out.keys()) == EXPECTED_KEYS          # schema still valid
        assert out["today_items"] == []                    # nothing invented
        assert any(s["status"] == "unavailable" for s in out["sources_used"])
        assert any(a["type"] == "clarification_needed" for a in out["actions"])
    finally:
        tools.SSOT_DB_PATH = old


def test_rag_down_still_ranks_tasks():
    old = tools.RAG_BASE_URL
    tools.RAG_BASE_URL = "http://127.0.0.1:9"   # closed port
    try:
        out = _run("daily")
        assert out["priority_suggestions"], "ranking must survive RAG being down"
        assert any(s["type"] == "rag_policy" and s["status"] == "unavailable"
                   for s in out["sources_used"])
    finally:
        tools.RAG_BASE_URL = old


def test_update_task_status_is_dry_run_by_default():
    r = tools.update_task_status(1002, "done", "test")
    assert r["ok"] and r["dry_run"] is True


def test_update_task_status_rejects_bad_status():
    assert tools.update_task_status(1, "finished")["ok"] is False


def test_unknown_tool_is_reported():
    assert tools.call_tool("nope")["ok"] is False


def test_tool_registry_matches_specs():
    assert {s["name"] for s in tools.TOOL_SPECS} == set(tools.TOOLS)


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as exc:               # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
