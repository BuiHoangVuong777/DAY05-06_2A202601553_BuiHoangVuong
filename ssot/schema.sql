-- =====================================================================
-- SSOT schema — project/task management for the hackathon demo.
-- SQLite. Dates are ISO-8601 TEXT in UTC ('now' is UTC in SQLite).
--
-- Run with:  sqlite3 ssot.db < schema.sql
-- Safe to re-run: every object is CREATE ... IF NOT EXISTS.
-- =====================================================================

PRAGMA foreign_keys = ON;   -- MUST be set per connection; SQLite defaults to OFF
PRAGMA journal_mode = WAL;

-- ---------------------------------------------------------------- users
CREATE TABLE IF NOT EXISTS users (
  id              INTEGER PRIMARY KEY,
  full_name       TEXT    NOT NULL,
  email           TEXT    NOT NULL UNIQUE,
  discord_handle  TEXT,
  is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------- teams
CREATE TABLE IF NOT EXISTS teams (
  id          INTEGER PRIMARY KEY,
  name        TEXT    NOT NULL UNIQUE,
  created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- --------------------------------------------------------- team_members
-- Composite PK stops the same user being added to a team twice.
-- A user may belong to only one team: enforced by the UNIQUE index below.
CREATE TABLE IF NOT EXISTS team_members (
  team_id       INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_in_team  TEXT    NOT NULL DEFAULT 'member'
                        CHECK (role_in_team IN ('leader', 'member')),
  joined_at     TEXT    NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (team_id, user_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_team_members_user ON team_members(user_id);

-- Team size ceiling. SQLite has no multi-row CHECK, so this is a trigger.
-- The floor (a team must reach 4) cannot be enforced on INSERT — a team
-- necessarily passes through 1, 2 and 3 members on the way to 4 — so it is
-- *verified* by v_team_integrity instead. See README.
CREATE TRIGGER IF NOT EXISTS trg_team_members_max4_insert
BEFORE INSERT ON team_members
WHEN (SELECT COUNT(*) FROM team_members WHERE team_id = NEW.team_id) >= 4
BEGIN
  SELECT RAISE(ABORT, 'team already has 4 members');
END;

CREATE TRIGGER IF NOT EXISTS trg_team_members_max4_update
BEFORE UPDATE OF team_id ON team_members
WHEN NEW.team_id <> OLD.team_id
 AND (SELECT COUNT(*) FROM team_members WHERE team_id = NEW.team_id) >= 4
BEGIN
  SELECT RAISE(ABORT, 'team already has 4 members');
END;

-- ------------------------------------------------------------- projects
-- id is t001..t100: the GLOB fixes the shape, the CAST fixes the range.
CREATE TABLE IF NOT EXISTS projects (
  id          TEXT    PRIMARY KEY
                      CHECK (id GLOB 't[0-9][0-9][0-9]'
                             AND CAST(substr(id, 2) AS INTEGER) BETWEEN 1 AND 100),
  name        TEXT    NOT NULL,
  team_id     INTEGER REFERENCES teams(id) ON DELETE SET NULL,
  status      TEXT    NOT NULL DEFAULT 'planned'
                      CHECK (status IN ('planned', 'active', 'blocked', 'done', 'archived')),
  start_date  TEXT,
  due_date    TEXT,
  created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_projects_team   ON projects(team_id);
CREATE INDEX IF NOT EXISTS ix_projects_status ON projects(status);

-- ---------------------------------------------------------------- tasks
-- Every task belongs to a project (NOT NULL FK). assignee is optional so an
-- unassigned backlog item is still representable.
CREATE TABLE IF NOT EXISTS tasks (
  id              INTEGER PRIMARY KEY,
  project_id      TEXT    NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title           TEXT    NOT NULL,
  description     TEXT    NOT NULL DEFAULT '',
  assignee_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  status          TEXT    NOT NULL DEFAULT 'todo'
                          CHECK (status IN ('todo', 'doing', 'blocked', 'done')),
  priority        INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
  progress        INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  due_at          TEXT,
  blocked_reason  TEXT    NOT NULL DEFAULT '',
  blocked_since   TEXT,
  created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
  -- A blocked task must say why; a non-blocked task must not carry a blocker.
  CHECK ((status = 'blocked' AND blocked_reason <> '' AND blocked_since IS NOT NULL)
      OR (status <> 'blocked' AND blocked_reason = ''  AND blocked_since IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_tasks_project  ON tasks(project_id);
CREATE INDEX IF NOT EXISTS ix_tasks_assignee ON tasks(assignee_id);
CREATE INDEX IF NOT EXISTS ix_tasks_due      ON tasks(due_at);
CREATE INDEX IF NOT EXISTS ix_tasks_status   ON tasks(status);

CREATE TRIGGER IF NOT EXISTS trg_tasks_touch
AFTER UPDATE ON tasks FOR EACH ROW
BEGIN
  UPDATE tasks SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- ------------------------------------------------------------ schedules
-- Demo calendar: standups, reviews, demo day. Scoped to a team, a project,
-- or neither (a programme-wide event).
CREATE TABLE IF NOT EXISTS schedules (
  id          INTEGER PRIMARY KEY,
  title       TEXT    NOT NULL,
  event_type  TEXT    NOT NULL DEFAULT 'meeting'
                      CHECK (event_type IN ('standup', 'meeting', 'review', 'workshop', 'deadline', 'demo')),
  team_id     INTEGER REFERENCES teams(id)    ON DELETE CASCADE,
  project_id  TEXT    REFERENCES projects(id) ON DELETE CASCADE,
  starts_at   TEXT    NOT NULL,
  ends_at     TEXT,
  location    TEXT    NOT NULL DEFAULT '',
  CHECK (ends_at IS NULL OR ends_at >= starts_at)
);
CREATE INDEX IF NOT EXISTS ix_schedules_start ON schedules(starts_at);
CREATE INDEX IF NOT EXISTS ix_schedules_team  ON schedules(team_id);

-- =====================================================================
-- Views — the agent's read surface. Each answers one demo question.
-- =====================================================================

-- Every open task, denormalised with the names an agent wants to say out loud.
CREATE VIEW IF NOT EXISTS v_open_tasks AS
SELECT
  t.id, t.title, t.status, t.priority, t.progress, t.due_at,
  t.blocked_reason, t.blocked_since,
  p.id   AS project_id, p.name AS project_name, p.status AS project_status,
  tm.id  AS team_id,    tm.name AS team_name,
  u.id   AS assignee_id, u.full_name AS assignee_name,
  CAST(julianday(t.due_at) - julianday('now') AS REAL) AS days_until_due
FROM tasks t
JOIN projects p    ON p.id = t.project_id
LEFT JOIN teams tm ON tm.id = p.team_id
LEFT JOIN users u  ON u.id = t.assignee_id
WHERE t.status <> 'done';

-- Priority score + the reasons behind it, so the agent can explain itself.
-- Mirrors the rule vocabulary used elsewhere in this repo (overdue / due soon /
-- blocked long / importance) rather than inventing a new one.
CREATE VIEW IF NOT EXISTS v_task_priority AS
SELECT
  v.*,
  (CASE WHEN v.due_at IS NOT NULL AND v.due_at < datetime('now')
        THEN 1000 + MIN(CAST((julianday('now') - julianday(v.due_at)) * 24 AS INTEGER), 500)
        WHEN v.due_at IS NOT NULL
        THEN MAX(0, 200 - CAST((julianday(v.due_at) - julianday('now')) * 24 AS INTEGER))
        ELSE 0 END)
  + v.priority * 10
  + (CASE WHEN v.status = 'blocked'
               AND julianday('now') - julianday(v.blocked_since) >= 2
          THEN 50 ELSE 0 END)                                       AS priority_score,
  TRIM(
    (CASE WHEN v.due_at IS NOT NULL AND v.due_at < datetime('now')
          THEN 'Quá hạn ' || CAST(ROUND(julianday('now') - julianday(v.due_at), 1) AS TEXT) || ' ngày · '
          WHEN v.due_at IS NOT NULL
               AND julianday(v.due_at) - julianday('now') <= 3
          THEN 'Sắp đến hạn · ' ELSE '' END)
    || 'Mức quan trọng ' || v.priority || '/5'
    || (CASE WHEN v.status = 'blocked'
                  AND julianday('now') - julianday(v.blocked_since) >= 2
             THEN ' · Đang kẹt ' || CAST(ROUND(julianday('now') - julianday(v.blocked_since), 1) AS TEXT) || ' ngày'
             WHEN v.status = 'blocked' THEN ' · Đang bị kẹt'
             ELSE '' END)
  ) AS priority_reason
FROM v_open_tasks v;

CREATE VIEW IF NOT EXISTS v_tasks_overdue AS
SELECT * FROM v_task_priority
WHERE due_at IS NOT NULL AND due_at < datetime('now')
ORDER BY priority_score DESC;

CREATE VIEW IF NOT EXISTS v_tasks_today AS
SELECT * FROM v_task_priority
WHERE due_at IS NOT NULL AND date(due_at) = date('now')
ORDER BY priority_score DESC;

-- "This week" = the current Monday-to-Sunday calendar week.
-- strftime('%w') is 0=Sunday, so (%w + 6) % 7 days back lands on Monday.
CREATE VIEW IF NOT EXISTS v_tasks_this_week AS
SELECT * FROM v_task_priority
WHERE due_at IS NOT NULL
  AND date(due_at) >= date('now', '-' || ((CAST(strftime('%w','now') AS INTEGER) + 6) % 7) || ' days')
  AND date(due_at) <  date('now', '-' || ((CAST(strftime('%w','now') AS INTEGER) + 6) % 7) || ' days', '+7 days')
ORDER BY due_at;

-- Due in the next 3 days and not yet overdue.
CREATE VIEW IF NOT EXISTS v_tasks_due_soon AS
SELECT * FROM v_task_priority
WHERE due_at IS NOT NULL
  AND due_at >= datetime('now')
  AND due_at <  datetime('now', '+3 days')
ORDER BY due_at;

CREATE VIEW IF NOT EXISTS v_tasks_blocked AS
SELECT * FROM v_task_priority
WHERE status = 'blocked'
ORDER BY blocked_since;

CREATE VIEW IF NOT EXISTS v_team_roster AS
SELECT tm.id AS team_id, tm.name AS team_name,
       u.id  AS user_id, u.full_name, u.email, u.discord_handle, m.role_in_team
FROM teams tm
JOIN team_members m ON m.team_id = tm.id
JOIN users u        ON u.id = m.user_id
ORDER BY tm.id, m.role_in_team DESC, u.full_name;

CREATE VIEW IF NOT EXISTS v_upcoming_schedule AS
SELECT s.id, s.title, s.event_type, s.starts_at, s.ends_at, s.location,
       tm.name AS team_name, p.id AS project_id
FROM schedules s
LEFT JOIN teams tm   ON tm.id = s.team_id
LEFT JOIN projects p ON p.id = s.project_id
WHERE s.starts_at >= datetime('now')
ORDER BY s.starts_at;

-- Integrity check: every row here is a violation. Expect zero rows.
CREATE VIEW IF NOT EXISTS v_team_integrity AS
SELECT t.id AS team_id, t.name AS team_name,
       COUNT(m.user_id) AS member_count,
       'team does not have exactly 4 members' AS problem
FROM teams t
LEFT JOIN team_members m ON m.team_id = t.id
GROUP BY t.id, t.name
HAVING COUNT(m.user_id) <> 4;
