# Progress agent — SSOT + RAG → fixed JSON

Reads tasks from the SQLite SSOT, rules from the RAG corpus, ranks with a
deterministic rule engine, and returns the same 7-key JSON every time.

```
mode (+ optional query)
  ├─ tools.py    → SSOT   (the only source of task facts)
  ├─ tools.py    → RAG    (rules/strategy only — never task facts)
  ├─ priority.py → score  (pure function, no LLM)
  └─ agent.py    → fixed 7-key JSON
```

| File | |
|---|---|
| `agent.py` | loop, modes, output assembly, CLI |
| `tools.py` | the 8 tools + SSOT/RAG clients + LLM-ready `TOOL_SPECS` |
| `priority.py` | the deterministic rule engine — **edit this to change ranking** |
| `test_agent.py` | 19 tests: rules, schema, degraded paths |

Standard library only. No dependencies to install.

## Run it

```bash
# 1. make the SSOT readable (it lives in a docker volume)
docker compose -f ssot/docker-compose.yml cp ssot:/data/ssot.db ./ssot/ssot.db

# 2. run
export SSOT_DB_PATH=./ssot/ssot.db
export RAG_BASE_URL=http://localhost:8000      # rag-app backend

python3 -m agent.agent --mode daily
python3 -m agent.agent --mode weekly
python3 -m agent.agent --mode weekly --query "Quy định nộp báo cáo tuần"
```

Flags: `--mode {daily,weekly}` · `--query <text>` · `--top-n N` · `--db PATH` · `--rag URL`.

**Exit code is 1 when the SSOT can't be read**, so a scheduler notices. Valid JSON
is still printed — with empty lists and a `clarification_needed` action, never
invented rows.

As a function:

```python
from agent.agent import run
report = run(mode="weekly", query="Gate là gì", top_n=5)   # -> dict
```

Tests: `python3 agent/test_agent.py` (or `python3 -m pytest agent/test_agent.py -q`).

## Modes

| | daily | weekly |
|---|---|---|
| `today_items` | ✅ | ✅ |
| `overdue_alerts` / `due_soon_alerts` | ✅ | ✅ |
| `week_items` | *empty by design* | ✅ |
| bottlenecks + milestone impact | — | ✅ (inside `priority_suggestions`) |

## Output

Exactly these keys, always, in this order:

```
today_items · week_items · overdue_alerts · due_soon_alerts
priority_suggestions · actions · sources_used
```

Each task item carries `task_id, title, deadline, status, priority, reason`
(plus `project_id, team, assignee, score`).

The schema is fixed, so anything that would need an eighth key rides inside it:

- **missing data / bad input** → `actions[type="clarification_needed"]`
- **source availability** → `sources_used[status="ok"|"unavailable"]`
- **non-task suggestions** → `priority_suggestions[kind="bottleneck"|"milestone_impact"]`

## Priority rules

All in `priority.py::RULES`. Each rule returns `(points, reason_fragment)`; the
score is the sum and the reason is the fragments joined, so **every ranking
explains itself** and `rules_fired` names the rules that contributed:

| Rule | Effect |
|---|---|
| `overdue` | `1000 + min(hours_late, 500)` — hard deadlines outrank everything |
| `due_today` | `+400` |
| `due_soon` | `+(200 − hours_until)`, within `DUE_SOON_DAYS` |
| `blocked` | `+150` if stuck ≥ `BLOCKED_LONG_DAYS`, else `+50` |
| `milestone_impact` | `+120` if due before an upcoming gate/demo/review for that team |
| `importance` | `+ priority × 20` |
| `nice_to_have` | `−100` for DB priority 1 |

Real output: `quá hạn 4.3 ngày · kẹt 5.3 ngày · ảnh hưởng mốc "Gate 2 — hạn nộp" · mức quan trọng 5/5` → score `1473.5`.

**To change ranking:** edit the tunables at the top of `priority.py`, or add a
function and append it to `RULES`. Nothing else needs touching.

## Adding a tool

1. Write the function in `tools.py` (return JSON-serialisable data).
2. Add it to `TOOLS` and add a schema entry to `TOOL_SPECS`.
3. Call it from `agent.run()`, or let an LLM call it via `tools.call_tool(name, **kw)`.

`TOOL_SPECS` is already in OpenAI/Anthropic function-calling shape, so the same
tools can be handed to a model without rewriting them.

## Safety

- **SSOT opens read-only** (`file:...?mode=ro`). The one exception is
  `update_task_status`, which takes its own read-write connection and is
  `dry_run=True` by default. The pipeline never calls it — status changes are a
  human decision.
- **RAG is policy-only.** No task status, deadline or assignee is ever read from
  it. If RAG is down, ranking is unaffected (it comes from the SSOT) and the gap
  is recorded in `sources_used`.
- **Nothing is inferred.** Every deadline/assignee/status is copied from the SSOT.

## Known limitations

- **"Tasks blocking other tasks" is not implemented.** The SSOT has no
  task-dependency table, so it cannot be derived without a schema change (which
  is out of scope here). Declared in `priority.UNIMPLEMENTABLE` and surfaced in
  every report as `actions[type="known_limitation"]`. The related requirement
  that *is* implemented is blocked-task boosting.
- **View names differ from the brief.** It referred to `v_tasks_week` and
  `v_tasks_priority`; the schema defines `v_tasks_this_week` and
  `v_task_priority`. The agent adapts to the real names — see the constants at
  the top of `tools.py`.
- **`get_upcoming_milestones` reads base tables, not `v_upcoming_schedule`**,
  because that view exposes `team_name` but not `team_id`, and the milestone rule
  needs the id to distinguish a team-scoped milestone from a programme-wide one.
- **Times are UTC**, matching the SSOT. "Today" shifts for a team working in
  UTC+7.
- The bundled SSOT contains **seeded demo data**, not real team progress.
