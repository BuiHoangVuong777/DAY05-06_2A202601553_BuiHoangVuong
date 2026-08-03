#!/usr/bin/env python3
"""Runnable eval suite for the progress agent.

`cases.json` is the spec (metadata, severity, coverage gaps); this file holds one
implementation per eval_id. The runner refuses to start if the two drift apart,
so a case can never be documented without being executed.

Cases are one of two determinism classes:
  invariant  — holds after any re-seed
  snapshot   — pinned to snapshot.json; regenerate with --refresh-snapshot

Usage:
    python3 -m agent.evals.run_evals                 # run everything
    python3 -m agent.evals.run_evals --only EV-PRIO  # prefix filter
    python3 -m agent.evals.run_evals --json report.json
    python3 -m agent.evals.run_evals --refresh-snapshot   # after FORCE_RESEED=1

Exit code: 1 if any blocker/major case FAILs, else 0. SKIP never fails the run
(a dependency being down is not a defect in the agent).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent import agent as agent_core, priority, tools  # noqa: E402

HERE = Path(__file__).resolve().parent
CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
SNAP_PATH = HERE / "snapshot.json"
CONTRACT = ["today_items", "week_items", "overdue_alerts", "due_soon_alerts",
            "priority_suggestions", "actions", "sources_used"]
REQUIRED_ITEM_FIELDS = {"task_id", "title", "deadline", "status", "priority", "reason"}

# Policy chunks quoted verbatim from output/rag_chunks.jsonl — not paraphrased.
POLICY = {
    "gate": {"ref": "cohort3_quality_control_demo_day.json/blocks/0",
             "text": "Gate không chặn team đi tiếp.\nGate dùng để đánh giá tiến độ.\n"
                     "Gate giúp Mentor đề xuất hỗ trợ khẩn cấp khi chưa đạt chuẩn."},
    "weekly": {"ref": "master_timeline.json/operating_notes/2"},
    "xp": {"ref": "cohort3_xp_system.json/blocks/0",
           "values": ["+5 XP", "+10 XP", "+100 XP"]},
    "demo_a": {"ref": "cohort3_evening_calendar.json/chunks/1", "dates": ["03/09", "04/09", "05/09"]},
    "demo_b": {"ref": "master_timeline.json/timeline/5", "dates": ["01/09"]},
}

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


# ----------------------------------------------------------------- utilities
def snapshot() -> dict:
    if not SNAP_PATH.exists():
        raise SystemExit(f"missing {SNAP_PATH}; run with --refresh-snapshot")
    return json.loads(SNAP_PATH.read_text(encoding="utf-8"))


def sql(query: str) -> list[dict]:
    con = sqlite3.connect(f"file:{tools.SSOT_DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(query).fetchall()]
    finally:
        con.close()


def parse(ts) -> dt.datetime | None:
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(str(ts).replace("Z", ""))
    except ValueError:
        return None


def http(path: str, body: dict, base: str | None = None) -> tuple[int, dict]:
    base = (base or tools.RAG_BASE_URL).rstrip("/")
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:  # noqa: BLE001
            return e.code, {}
    except Exception as exc:  # noqa: BLE001
        raise ConnectionError(str(exc)) from exc


def backend_up() -> bool:
    try:
        http("/api/query", {"question": "ping", "top_k": 1})
        return True
    except ConnectionError:
        return False


def ai_mode() -> bool:
    """Answer-content cases need real generation; retrieval-only can't be graded."""
    try:
        _, d = http("/api/query", {"question": "ping", "top_k": 1})
        return d.get("mode") == "ai"
    except ConnectionError:
        return False


def fixture(**kw) -> dict:
    base = {"id": 1, "title": "t", "status": "todo", "priority": 3,
            "due_at": None, "blocked_since": None, "team_id": 1}
    base.update(kw)
    return base


def verdict(cond: bool, detail: str) -> tuple[str, str]:
    return (PASS if cond else FAIL), detail


NOW = dt.datetime(2026, 7, 30, 12, 0, 0)   # fixed clock for rule fixtures
def rel(days=0, hours=0) -> str:
    return (NOW + dt.timedelta(days=days, hours=hours)).isoformat(sep=" ")


# --------------------------------------------------------------- SSOT / data
def ev_ssot_001():
    r = sql("""SELECT (SELECT COUNT(*) FROM users) u,(SELECT COUNT(*) FROM teams) t,
               (SELECT COUNT(*) FROM projects) p,(SELECT COUNT(*) FROM v_team_integrity) bad""")[0]
    return verdict(r == {"u": 20, "t": 5, "p": 100, "bad": 0}, str(r))


def ev_ssot_002():
    r = sql("SELECT MIN(id) lo, MAX(id) hi, COUNT(DISTINCT id) n FROM projects")[0]
    bad = sql("SELECT COUNT(*) c FROM projects WHERE id NOT GLOB 't[0-9][0-9][0-9]'")[0]["c"]
    return verdict(r["lo"] == "t001" and r["hi"] == "t100" and r["n"] == 100 and bad == 0,
                   f"{r}, malformed={bad}")


def ev_ssot_003():
    rows = sql("SELECT team_id, COUNT(*) c FROM team_members GROUP BY team_id ORDER BY team_id")
    return verdict(len(rows) == 5 and all(x["c"] == 4 for x in rows),
                   ", ".join(f"team{x['team_id']}={x['c']}" for x in rows))


def ev_ssot_004():
    got = sql("SELECT user_id, full_name, role_in_team FROM v_team_roster "
              "WHERE team_id=1 ORDER BY user_id")
    exp = snapshot()["team1_roster"]
    return verdict(got == exp, f"{len(got)} members; leader={got[0]['role_in_team'] if got else None}")


# ------------------------------------------------------------------- daily
def ev_daily_001():
    out = agent_core.run(mode="daily")
    return verdict(list(out.keys()) == CONTRACT, f"keys={list(out.keys())}")


def ev_daily_002():
    return verdict(agent_core.run(mode="daily")["week_items"] == [], "week_items empty")


def ev_daily_003():
    out = agent_core.run(mode="daily")
    bad = []
    for key in ("today_items", "overdue_alerts", "due_soon_alerts"):
        for it in out[key]:
            if not REQUIRED_ITEM_FIELDS <= set(it):
                bad.append(f"{key}#{it.get('task_id')} missing fields")
            elif not it.get("reason"):
                bad.append(f"{key}#{it.get('task_id')} empty reason")
    n = sum(len(out[k]) for k in ("today_items", "overdue_alerts", "due_soon_alerts"))
    return verdict(not bad, f"{n} items checked" if not bad else "; ".join(bad[:3]))


def ev_daily_004():
    out = agent_core.run(mode="daily")
    today = priority.utc_now().date()
    bad = [i["task_id"] for i in out["today_items"]
           if (parse(i["deadline"]) or dt.datetime.min).date() != today]
    return verdict(not bad, f"{len(out['today_items'])} items, {len(bad)} off-date")


# ----------------------------------------------------------------- overdue
def ev_overdue_001():
    out = agent_core.run(mode="daily")
    now = priority.utc_now()
    bad = [i["task_id"] for i in out["overdue_alerts"]
           if not (parse(i["deadline"]) and parse(i["deadline"]) < now) or i["status"] == "done"]
    return verdict(not bad, f"{len(out['overdue_alerts'])} alerts, {len(bad)} violations")


def ev_overdue_002():
    n = sql("SELECT COUNT(*) c FROM v_tasks_overdue")[0]["c"]
    exp = snapshot()["counts"]["overdue"]
    return verdict(n == exp, f"overdue={n}, snapshot={exp}")


def ev_overdue_003():
    got = sql("SELECT id,project_id,team_name,title,assignee_name,status,priority "
              "FROM v_task_priority ORDER BY priority_score DESC, id LIMIT 1")[0]
    exp = snapshot()["top_priority_task"]
    return verdict(got == exp, f"top={got['id']} {got['title'][:24]}")


# ---------------------------------------------------------------- due soon
def ev_duesoon_001():
    out = agent_core.run(mode="daily")
    now = priority.utc_now()
    horizon = now + dt.timedelta(days=priority.DUE_SOON_DAYS)
    bad = [i["task_id"] for i in out["due_soon_alerts"]
           if not (parse(i["deadline"]) and now <= parse(i["deadline"]) < horizon)]
    return verdict(not bad, f"{len(out['due_soon_alerts'])} alerts, {len(bad)} outside window")


# ------------------------------------------------------------------ weekly
def ev_weekly_001():
    out = agent_core.run(mode="weekly")
    return verdict(list(out.keys()) == CONTRACT and len(out["week_items"]) > 0,
                   f"week_items={len(out['week_items'])}")


def ev_weekly_002():
    kinds = {p.get("kind") for p in agent_core.run(mode="weekly")["priority_suggestions"]}
    return verdict({"task", "bottleneck", "milestone_impact"} <= kinds, f"kinds={sorted(k for k in kinds if k)}")


def ev_weekly_003():
    bn = [p for p in agent_core.run(mode="weekly")["priority_suggestions"]
          if p.get("kind") == "bottleneck"]
    exp = snapshot()["bottleneck"]
    ok = (len(bn) == 1 and bn[0]["blocker"] == exp["blocker"]
          and bn[0]["task_count"] == exp["task_count"]
          and len(bn[0]["teams_affected"]) == exp["teams_affected_count"])
    detail = f"{len(bn)} group(s)" + (f", {bn[0]['task_count']} tasks" if bn else "")
    return verdict(ok, detail)


def ev_weekly_004():
    got = sql("SELECT id,title,event_type,team_id FROM schedules "
              "WHERE event_type IN ('deadline','demo','review') ORDER BY starts_at")
    return verdict(got == snapshot()["milestones"], f"{len(got)} milestones")


# -------------------------------------------------------------- rule engine
def ev_prio_001():
    a = priority.score_task(fixture(id=1, due_at=rel(days=-2)), NOW)["agent_score"]
    b = priority.score_task(fixture(id=2, due_at=rel(hours=11)), NOW)["agent_score"]
    c = priority.score_task(fixture(id=3, due_at=rel(days=21), priority=5), NOW)["agent_score"]
    return verdict(a > b > c, f"overdue={a} > today={b} > future={c}")


def ev_prio_002():
    lo = priority.score_task(fixture(status="blocked", blocked_since=rel(days=-5)), NOW)
    hi = priority.score_task(fixture(status="blocked", blocked_since=rel(hours=-6)), NOW)
    delta = lo["agent_score"] - hi["agent_score"]
    return verdict(delta == 100 and "kẹt" in lo["agent_reason"], f"delta={delta}")


def ev_prio_003():
    ms = [{"title": "Gate 2", "team_id": 1, "_starts": NOW + dt.timedelta(days=3)}]
    a = priority.score_task(fixture(team_id=1, due_at=rel(days=2)), NOW, ms)
    b = priority.score_task(fixture(team_id=2, due_at=rel(days=2)), NOW, ms)
    delta = a["agent_score"] - b["agent_score"]
    return verdict(delta == 120 and "ảnh hưởng mốc" in a["agent_reason"], f"delta={delta}")


def ev_prio_004():
    n = priority.score_task(fixture(priority=1), NOW)
    m = priority.score_task(fixture(priority=3), NOW)
    return verdict(n["agent_score"] < m["agent_score"] and "nice-to-have" in n["agent_reason"],
                   f"nice={n['agent_score']} < normal={m['agent_score']}")


def ev_prio_005():
    f = fixture(due_at=rel(days=-2), status="blocked", blocked_since=rel(days=-4), priority=5)
    a, b = priority.score_task(f, NOW), priority.score_task(f, NOW)
    return verdict(a["agent_score"] == b["agent_score"] and a["agent_reason"] == b["agent_reason"],
                   f"score={a['agent_score']} stable")


def ev_prio_006():
    names = {n for n, _ in priority.RULES}
    tasks = [p for p in agent_core.run(mode="daily")["priority_suggestions"]
             if p.get("kind") == "task"]
    bad = [t["task_id"] for t in tasks
           if not t.get("rules_fired") or not set(t["rules_fired"]) <= names]
    return verdict(tasks and not bad, f"{len(tasks)} task suggestions, {len(bad)} bad")


# ---------------------------------------------------------------- policy
def _policy_refs(query: str, top_k: int = 5) -> tuple[list[str], dict]:
    _, d = http("/api/query", {"question": query, "top_k": top_k})
    return [f"{s.get('source_file','')}{s.get('source_pointer','')}" for s in d.get("sources", [])], d


def ev_policy_001():
    if not backend_up():
        return SKIP, "backend not reachable"
    refs, d = _policy_refs("Gate là gì và dùng để làm gì")
    got = POLICY["gate"]["ref"] in refs
    lied = "chặn team" in d.get("answer", "") and "không chặn" not in d.get("answer", "")
    return verdict(got and not lied, f"retrieved={got}, contradicts_policy={lied}")


def ev_policy_002():
    if not backend_up():
        return SKIP, "backend not reachable"
    refs, _ = _policy_refs("Quy định nộp báo cáo tuần và weekly report")
    return verdict(POLICY["weekly"]["ref"] in refs, f"top={refs[0] if refs else None}")


def ev_policy_003():
    if not backend_up():
        return SKIP, "backend not reachable"
    refs, d = _policy_refs("Làm sao để kiếm XP")
    if POLICY["xp"]["ref"] not in refs:
        return FAIL, f"XP chunk not retrieved; got {refs[:2]}"
    if d.get("mode") != "ai":
        return SKIP, "fallback mode — XP values in the answer cannot be graded"
    ans = d.get("answer", "")
    missing = [v for v in POLICY["xp"]["values"] if v.replace(" ", "") not in ans.replace(" ", "")]
    return verdict(not missing, f"missing={missing}" if missing else "all XP values exact")


def ev_policy_004():
    if not backend_up():
        return SKIP, "backend not reachable"
    _, d = http("/api/query", {"question": "Gate 2 yêu cầu nộp gì?", "top_k": 3})
    srcs = d.get("sources", [])
    bad = [s for s in srcs if not all(k in s for k in ("source_file", "source_pointer", "score"))]
    return verdict(srcs and not bad, f"{len(srcs)} sources, {len(bad)} incomplete")


# -------------------------------------------------------------- negatives
def ev_neg_001():
    old = tools.SSOT_DB_PATH
    tools.SSOT_DB_PATH = "/nonexistent/missing.db"
    try:
        out = agent_core.run(mode="daily")
        ok = (list(out.keys()) == CONTRACT
              and all(out[k] == [] for k in ("today_items", "overdue_alerts",
                                             "due_soon_alerts", "priority_suggestions"))
              and any(s.get("type") == "ssot" and s.get("status") == "unavailable"
                      for s in out["sources_used"])
              and any(a.get("type") == "clarification_needed" for a in out["actions"]))
        return verdict(ok, "empty lists + unavailable source + clarification")
    finally:
        tools.SSOT_DB_PATH = old


def ev_neg_002():
    up = agent_core.run(mode="daily")
    old = tools.RAG_BASE_URL
    tools.RAG_BASE_URL = "http://127.0.0.1:9"      # closed port
    try:
        down = agent_core.run(mode="daily")
    finally:
        tools.RAG_BASE_URL = old
    ids_up = [p["task_id"] for p in up["priority_suggestions"] if p.get("kind") == "task"]
    ids_down = [p["task_id"] for p in down["priority_suggestions"] if p.get("kind") == "task"]
    degraded = any(s.get("type") == "rag_policy" and s.get("status") == "unavailable"
                   for s in down["sources_used"])
    return verdict(bool(ids_down) and ids_up == ids_down and degraded,
                   f"ranking identical={ids_up == ids_down}, degradation recorded={degraded}")


def ev_neg_003():
    out = agent_core.run(mode="monthly")
    ok = (list(out.keys()) == CONTRACT
          and all(out[k] == [] for k in CONTRACT if k != "actions")
          and any(a.get("type") == "clarification_needed" and a.get("field") == "mode"
                  for a in out["actions"]))
    return verdict(ok, "refused with clarification_needed(field=mode)")


def ev_neg_004():
    if not backend_up():
        return SKIP, "backend not reachable"
    _, d = http("/api/query", {"question": "Demo Day diễn ra ngày nào?", "top_k": 5})
    if d.get("mode") != "ai":
        return SKIP, "fallback mode — answer content cannot be graded"
    ans = d.get("answer", "")
    a = any(x in ans for x in POLICY["demo_a"]["dates"])
    b = any(x in ans for x in POLICY["demo_b"]["dates"])
    flagged = any(w in ans.lower() for w in ("mâu thuẫn", "không khớp", "khác nhau", "trái ngược"))
    return verdict((a and b) or flagged,
                   f"calendar_dates={a}, timeline_date={b}, conflict_flagged={flagged}")


def ev_neg_005():
    if not backend_up():
        return SKIP, "backend not reachable"
    _, d = http("/api/query", {"question": "Thời tiết Hà Nội ngày mai thế nào?", "top_k": 3})
    if d.get("mode") != "ai":
        return SKIP, "fallback mode — refusal cannot be graded"
    ans = d.get("answer", "").lower()
    # Kiểm tra TÍNH CHẤT chứ không bắt đúng một câu chữ: (a) có nói rõ tài liệu
    # không phủ, và (b) không bịa ra số liệu thời tiết. Danh sách cụm từ đã được
    # nới cho khớp cách diễn đạt mà SYSTEM_PROMPT hiện tại quy định.
    cum_tu_tu_choi = ("không tìm thấy", "không có trong tài liệu", "không đề cập",
                      "không cung cấp", "không có thông tin", "chưa nói đủ",
                      "không nêu rõ", "không thể cung cấp", "chưa đề cập")
    declined = any(p in ans for p in cum_tu_tu_choi)
    # Chống bịa: câu trả lời không được chứa số đo thời tiết cụ thể.
    bia_dat = bool(re.search(r"\d+\s*(°|độ c|độ|mm mưa)", ans))
    return verdict(declined and not bia_dat,
                   f"declined={declined}, fabricated_weather={bia_dat}")


def ev_neg_006():
    out = agent_core.run(mode="weekly")
    rows = {r["id"]: r for r in sql(
        "SELECT id,title,status,priority,due_at FROM v_task_priority")}
    bad = []
    for key in ("today_items", "overdue_alerts", "due_soon_alerts", "week_items"):
        for it in out[key]:
            src = rows.get(it["task_id"])
            if not src:
                bad.append(f"{it['task_id']} not in SSOT")
            elif (it["title"], it["status"], it["priority"], it["deadline"]) != \
                 (src["title"], src["status"], src["priority"], src["due_at"]):
                bad.append(f"{it['task_id']} field mismatch")
    return verdict(not bad, f"{len(rows)} SSOT rows cross-checked" if not bad else "; ".join(bad[:3]))


def ev_neg_007():
    if not backend_up():
        return SKIP, "backend not reachable"
    status, _ = http("/api/query", {"question": ""})
    return verdict(status == 422, f"HTTP {status}")


# ------------------------------------------------------------ write safety
def ev_write_001():
    before = sql("SELECT status FROM tasks WHERE id=1002")
    r = tools.update_task_status(1002, "done", "eval probe")
    after = sql("SELECT status FROM tasks WHERE id=1002")
    return verdict(r.get("ok") and r.get("dry_run") is True and before == after,
                   f"dry_run={r.get('dry_run')}, status unchanged={before == after}")


def ev_write_002():
    r = tools.update_task_status(1002, "finished")
    return verdict(r.get("ok") is False and "status must be one of" in r.get("error", ""),
                   r.get("error", "")[:60])


def ev_write_003():
    digest = lambda: hashlib.sha256(Path(tools.SSOT_DB_PATH).read_bytes()).hexdigest()
    before = digest()
    agent_core.run(mode="weekly")
    after = digest()
    return verdict(before == after, f"sha256 {'unchanged' if before == after else 'CHANGED'}")


REGISTRY = {
    "EV-SSOT-001": ev_ssot_001, "EV-SSOT-002": ev_ssot_002, "EV-SSOT-003": ev_ssot_003,
    "EV-SSOT-004": ev_ssot_004,
    "EV-DAILY-001": ev_daily_001, "EV-DAILY-002": ev_daily_002,
    "EV-DAILY-003": ev_daily_003, "EV-DAILY-004": ev_daily_004,
    "EV-OVERDUE-001": ev_overdue_001, "EV-OVERDUE-002": ev_overdue_002,
    "EV-OVERDUE-003": ev_overdue_003,
    "EV-DUESOON-001": ev_duesoon_001,
    "EV-WEEKLY-001": ev_weekly_001, "EV-WEEKLY-002": ev_weekly_002,
    "EV-WEEKLY-003": ev_weekly_003, "EV-WEEKLY-004": ev_weekly_004,
    "EV-PRIO-001": ev_prio_001, "EV-PRIO-002": ev_prio_002, "EV-PRIO-003": ev_prio_003,
    "EV-PRIO-004": ev_prio_004, "EV-PRIO-005": ev_prio_005, "EV-PRIO-006": ev_prio_006,
    "EV-POLICY-001": ev_policy_001, "EV-POLICY-002": ev_policy_002,
    "EV-POLICY-003": ev_policy_003, "EV-POLICY-004": ev_policy_004,
    "EV-NEG-001": ev_neg_001, "EV-NEG-002": ev_neg_002, "EV-NEG-003": ev_neg_003,
    "EV-NEG-004": ev_neg_004, "EV-NEG-005": ev_neg_005, "EV-NEG-006": ev_neg_006,
    "EV-NEG-007": ev_neg_007,
    "EV-WRITE-001": ev_write_001, "EV-WRITE-002": ev_write_002, "EV-WRITE-003": ev_write_003,
}


def refresh_snapshot() -> None:
    """Re-derive the snapshot-bound expectations from the current SSOT."""
    snap = {
        "now_utc": sql("SELECT datetime('now') n")[0]["n"],
        "counts": sql("""SELECT (SELECT COUNT(*) FROM users) users,(SELECT COUNT(*) FROM teams) teams,
            (SELECT COUNT(*) FROM projects) projects,(SELECT COUNT(*) FROM tasks) tasks,
            (SELECT COUNT(*) FROM v_tasks_overdue) overdue,(SELECT COUNT(*) FROM v_tasks_today) today,
            (SELECT COUNT(*) FROM v_tasks_due_soon) due_soon,
            (SELECT COUNT(*) FROM v_tasks_this_week) this_week,
            (SELECT COUNT(*) FROM v_tasks_blocked) blocked""")[0],
        "top_priority_task": sql("SELECT id,project_id,team_name,title,assignee_name,status,priority "
                                 "FROM v_task_priority ORDER BY priority_score DESC, id LIMIT 1")[0],
        "bottleneck": sql("SELECT blocked_reason blocker, COUNT(*) task_count, "
                          "COUNT(DISTINCT team_name) teams_affected_count "
                          "FROM v_tasks_blocked GROUP BY 1")[0],
        "milestones": sql("SELECT id,title,event_type,team_id FROM schedules "
                          "WHERE event_type IN ('deadline','demo','review') ORDER BY starts_at"),
        "team1_roster": sql("SELECT user_id,full_name,role_in_team FROM v_team_roster "
                            "WHERE team_id=1 ORDER BY user_id"),
        "probe_task": sql("SELECT id,title,status,project_id,team_name,assignee_name "
                          "FROM v_task_priority WHERE id=1002")[0],
    }
    SNAP_PATH.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"snapshot refreshed -> {SNAP_PATH}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run the agent eval suite.")
    ap.add_argument("--only", help="run eval_ids starting with this prefix")
    ap.add_argument("--json", help="write the machine-readable report here")
    ap.add_argument("--refresh-snapshot", action="store_true",
                    help="re-derive snapshot-bound expectations, then exit")
    args = ap.parse_args(argv)

    if args.refresh_snapshot:
        refresh_snapshot()
        return 0

    # Spec and implementations must not drift.
    spec = {c["eval_id"]: c for c in CASES["cases"]}
    if set(spec) != set(REGISTRY):
        print(f"spec/impl mismatch — unimplemented: {sorted(set(spec) - set(REGISTRY))}, "
              f"undocumented: {sorted(set(REGISTRY) - set(spec))}", file=sys.stderr)
        return 2

    selected = [c for c in CASES["cases"]
                if not args.only or c["eval_id"].startswith(args.only)]
    results, counts = [], {PASS: 0, FAIL: 0, SKIP: 0}

    print(f"SSOT: {tools.SSOT_DB_PATH}   RAG: {tools.RAG_BASE_URL}")
    print(f"SSOT authenticity: {CASES['ssot_authenticity']['status']} "
          f"— {CASES['ssot_authenticity']['detail'][:88]}…\n")

    for case in selected:
        eid = case["eval_id"]
        try:
            status, detail = REGISTRY[eid]()
        except Exception as exc:  # noqa: BLE001 - an erroring case is a failing case
            status, detail = FAIL, f"{type(exc).__name__}: {exc}"
        counts[status] += 1
        results.append({**case, "status": status, "detail": detail})
        mark = {PASS: "PASS", FAIL: "FAIL", SKIP: "SKIP"}[status]
        flag = "" if status != FAIL else f"  [{case['severity']}]"
        print(f"{mark}  {eid:<16} {case['determinism']:<9} {detail[:70]}{flag}")

    blocking = [r for r in results if r["status"] == FAIL
                and r["severity"] in ("blocker", "major")]
    print(f"\n{counts[PASS]} passed · {counts[FAIL]} failed · {counts[SKIP]} skipped "
          f"({len(blocking)} blocking)")

    if args.json:
        report = {
            "suite_id": CASES["suite_id"],
            "run_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "ssot_authenticity": CASES["ssot_authenticity"],
            "ssot_db_path": tools.SSOT_DB_PATH,
            "totals": {"passed": counts[PASS], "failed": counts[FAIL],
                       "skipped": counts[SKIP], "blocking_failures": len(blocking)},
            "results": results,
            "not_covered": CASES["not_covered"],
        }
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
        print(f"report -> {args.json}")

    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
