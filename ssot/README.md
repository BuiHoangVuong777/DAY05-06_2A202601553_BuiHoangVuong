# SSOT — SQLite single source of truth

Projects, tasks, teams and schedule for the hackathon demo. The agent reads this
DB to answer "what should we do next, and why".

```
users ──< team_members >── teams ──< projects ──< tasks
                                        └──────< schedules >── teams
```

| File | |
|---|---|
| `schema.sql` | DDL, triggers, and the query views. Re-runnable (`IF NOT EXISTS`). |
| `seed.sql` | 20 users · 5 teams · 100 projects · 90 tasks · 14 schedule entries. Idempotent. |
| `Dockerfile` / `docker-compose.yml` / `entrypoint.sh` | Container with a persistent volume + web UI. |

## Run locally

```bash
cd ssot
rm -f ssot.db
sqlite3 ssot.db < schema.sql
sqlite3 ssot.db < seed.sql
```

No `sqlite3` CLI? Python has SQLite built in:

```bash
python3 -c "
import sqlite3,pathlib
db=sqlite3.connect('ssot.db')
db.executescript(pathlib.Path('schema.sql').read_text())
db.executescript(pathlib.Path('seed.sql').read_text())
print(db.execute('SELECT COUNT(*) FROM projects').fetchone())"
```

**`PRAGMA foreign_keys = ON` is per-connection and SQLite defaults it OFF.** The
scripts set it, but so must anything else that writes — otherwise foreign keys are
silently unenforced.

## Run in Docker

```bash
cd ssot
docker compose up -d --build      # one command: init + seed + web UI
```

- Web UI: **<http://localhost:8081>** (browse tables, run ad-hoc SQL)
- The DB lives in the named volume `ssot-data`, so it survives `down`/`up`.
- The entrypoint only seeds when the file is absent, and refuses to start if any
  team is not exactly 4 members.

```bash
FORCE_RESEED=1 docker compose up -d --force-recreate   # wipe + rebuild
docker compose down -v                                 # also delete the volume
```

## Inspect

```bash
# CLI inside the container
docker compose exec ssot sqlite3 -header -column /data/ssot.db \
  "SELECT * FROM v_tasks_today LIMIT 5;"

# interactive shell
docker compose exec ssot sqlite3 /data/ssot.db

# locally
sqlite3 -header -column ssot.db "SELECT * FROM v_tasks_overdue LIMIT 5;"
```

## Demo queries

Every question in the brief is one `SELECT * FROM <view>` — no joins to write:

| Question | Query |
|---|---|
| Today's tasks | `SELECT * FROM v_tasks_today;` |
| This week's tasks | `SELECT * FROM v_tasks_this_week;` |
| Overdue | `SELECT * FROM v_tasks_overdue;` |
| Due soon (next 3 days) | `SELECT * FROM v_tasks_due_soon;` |
| Top priority **with reasons** | `SELECT * FROM v_task_priority ORDER BY priority_score DESC LIMIT 10;` |
| Blocked | `SELECT * FROM v_tasks_blocked;` |
| Team roster | `SELECT * FROM v_team_roster WHERE team_id = 1;` |
| Upcoming schedule | `SELECT * FROM v_upcoming_schedule;` |
| Data problems (expect 0 rows) | `SELECT * FROM v_team_integrity;` |

`v_task_priority` returns a `priority_score` and a human-readable
`priority_reason`, e.g. *"Quá hạn 4.0 ngày · Mức quan trọng 5/5 · Đang kẹt 5.0 ngày"* —
so the agent can explain a ranking instead of asserting it. Scoring mirrors the
rule vocabulary already used elsewhere in this repo (overdue / due soon /
blocked-long / importance).

Scoped to one team:

```sql
SELECT * FROM v_task_priority WHERE team_id = 1 ORDER BY priority_score DESC LIMIT 5;
```

## What is enforced

| Rule | How |
|---|---|
| Project ids are `t001`..`t100` | `CHECK (id GLOB 't[0-9][0-9][0-9]' AND CAST(substr(id,2) AS INTEGER) BETWEEN 1 AND 100)` |
| Every task references a project | `project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE` |
| Team members reference a real user and team | Explicit `REFERENCES` + `PRAGMA foreign_keys = ON` |
| A user belongs to at most one team | `UNIQUE INDEX ux_team_members_user(user_id)` |
| **No team exceeds 4 members** | `BEFORE INSERT` / `BEFORE UPDATE` triggers that `RAISE(ABORT)` |
| A blocked task must state why | Table-level `CHECK` tying `status='blocked'` to `blocked_reason` + `blocked_since` |

**The "exactly 4" floor is verified, not enforced.** A team necessarily passes
through 1, 2 and 3 members while being populated, so no `INSERT`-time rule can
require 4. The ceiling is a hard trigger; the floor is checked by
`v_team_integrity` (every row is a violation — expect zero), asserted at the end
of `seed.sql`, and re-checked by the container entrypoint, which refuses to start
if it fails.

## Seeding notes

Re-running `seed.sql` is safe: every statement is `INSERT OR REPLACE` with fixed
primary keys, so a second run resets the demo rows instead of duplicating them
(verified: counts stay 100/90/20). It does **not** delete rows you added yourself.

**Deadlines are relative to seed time** (`datetime('now','+N days')`), so the demo
always has genuinely overdue, due-today and due-soon tasks whenever you seed —
there is no date that goes stale. Re-seed with `FORCE_RESEED=1` to re-centre them
on today.

Shape of the seeded data: 100 projects round-robin across 5 teams (20 each), of
which **15 are `active`** — only those carry tasks, so "today's tasks" stays
demo-sized rather than returning hundreds of rows. The rest are
planned/blocked/done/archived backlog. Each active project gets 6 tasks spread
deliberately across overdue+blocked, overdue, due-today, due-in-2-days, next-week
and done, so **every view above returns rows**.
