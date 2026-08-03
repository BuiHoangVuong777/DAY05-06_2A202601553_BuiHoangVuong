-- =====================================================================
-- Seed data. IDEMPOTENT: every statement is INSERT OR REPLACE with fixed
-- primary keys, so re-running resets the demo data to a known state without
-- duplicating rows. Run after schema.sql:
--   sqlite3 ssot.db < schema.sql && sqlite3 ssot.db < seed.sql
--
-- Deadlines are RELATIVE to run time (datetime('now', '+N days')), so the
-- demo always has genuinely overdue / due-today / due-soon tasks whenever
-- you run it — no re-seeding needed on a later date.
-- =====================================================================

PRAGMA foreign_keys = ON;

BEGIN;

-- ---------------------------------------------------------------- users
-- 20 users = 5 teams x 4. Emails are example.test (RFC 6761 reserved).
INSERT OR REPLACE INTO users (id, full_name, email, discord_handle) VALUES
  ( 1, 'Bùi Hoàng Vương',    'vuong.bh@example.test',   'vuongbh'),
  ( 2, 'Đặng Tiến Thành',    'thanh.dt@example.test',   'thanhdt'),
  ( 3, 'Phạm Xuân Phong',    'phong.px@example.test',   'phongpx'),
  ( 4, 'Nguyễn Thu Hà',      'ha.nt@example.test',      'hant'),
  ( 5, 'Lê Minh Quân',       'quan.lm@example.test',    'quanlm'),
  ( 6, 'Trần Khánh Linh',    'linh.tk@example.test',    'linhtk'),
  ( 7, 'Vũ Đình Nam',        'nam.vd@example.test',     'namvd'),
  ( 8, 'Hoàng Thị Mai',      'mai.ht@example.test',     'maiht'),
  ( 9, 'Đỗ Anh Tuấn',        'tuan.da@example.test',    'tuanda'),
  (10, 'Ngô Bảo Châu',       'chau.nb@example.test',    'chaunb'),
  (11, 'Lý Thanh Tùng',      'tung.lt@example.test',    'tunglt'),
  (12, 'Phan Diệu Linh',     'linh.pd@example.test',    'linhpd'),
  (13, 'Trịnh Công Sơn',     'son.tc@example.test',     'sontc'),
  (14, 'Bùi Khánh Vy',       'vy.bk@example.test',      'vybk'),
  (15, 'Dương Quốc Đạt',     'dat.dq@example.test',     'datdq'),
  (16, 'Mai Phương Thảo',    'thao.mp@example.test',    'thaomp'),
  (17, 'Cao Việt Hùng',      'hung.cv@example.test',    'hungcv'),
  (18, 'Tạ Thu Trang',       'trang.tt@example.test',   'trangtt'),
  (19, 'Hồ Gia Bảo',         'bao.hg@example.test',     'baohg'),
  (20, 'Đinh Nhật Minh',     'minh.dn@example.test',    'minhdn');

-- ---------------------------------------------------------------- teams
INSERT OR REPLACE INTO teams (id, name) VALUES
  (1, 'Team Alpha'),
  (2, 'Team Bravo'),
  (3, 'Team Charlie'),
  (4, 'Team Delta'),
  (5, 'Team Echo');

-- --------------------------------------------------------- team_members
-- Users 1-4 -> team 1, 5-8 -> team 2, ... exactly 4 each.
-- The first member of each team is the leader.
-- NOTE: uses INSERT OR REPLACE so a re-run is a no-op. A plain INSERT of a
-- 5th member into any team is rejected by trg_team_members_max4_insert.
INSERT OR REPLACE INTO team_members (team_id, user_id, role_in_team)
WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 20)
SELECT ((n - 1) / 4) + 1,
       n,
       CASE WHEN (n - 1) % 4 = 0 THEN 'leader' ELSE 'member' END
FROM seq;

-- ------------------------------------------------------------- projects
-- 100 projects, t001..t100, spread round-robin across the 5 teams.
-- Only the first 3 projects of each team are 'active' so "today's tasks"
-- stays demo-sized; the rest are planned/done/archived backlog.
INSERT OR REPLACE INTO projects (id, name, team_id, status, start_date, due_date)
WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 100)
SELECT
  printf('t%03d', n),
  printf('Dự án %03d — %s', n,
         CASE n % 5
           WHEN 0 THEN 'Nền tảng dữ liệu'

           WHEN 1 THEN 'Trợ lý AI'
           WHEN 2 THEN 'Cổng thông tin'
           WHEN 3 THEN 'Ứng dụng di động'
           ELSE        'Tự động hoá quy trình'
         END),
  ((n - 1) % 5) + 1,
  CASE
    WHEN ((n - 1) / 5) < 3  THEN 'active'
    WHEN ((n - 1) / 5) < 6  THEN 'planned'
    WHEN ((n - 1) / 5) < 8  THEN 'blocked'
    WHEN ((n - 1) / 5) < 16 THEN 'done'
    ELSE                         'archived'
  END,
  date('now', '-' || (30 + n % 30) || ' days'),
  date('now', '+' || (n % 45) || ' days')
FROM seq;

-- ---------------------------------------------------------------- tasks
-- 6 tasks per active project (15 active projects => 90 tasks), each with a
-- deliberate spread so every demo view returns rows:
--   k=0 overdue+blocked   k=1 overdue    k=2 due today
--   k=3 due in 2 days     k=4 next week  k=5 done
INSERT OR REPLACE INTO tasks
  (id, project_id, title, description, assignee_id, status, priority, progress,
   due_at, blocked_reason, blocked_since)
WITH RECURSIVE
  seq(n) AS (SELECT 0 UNION ALL SELECT n + 1 FROM seq WHERE n < 89),
  -- Number the active projects and the members of each team so the spread can
  -- be a plain JOIN. (A correlated column is not allowed in a subquery OFFSET.)
  ap AS (
    SELECT id, team_id, ROW_NUMBER() OVER (ORDER BY id) - 1 AS ix
    FROM projects WHERE status = 'active'
  ),
  tmn AS (
    SELECT team_id, user_id,
           ROW_NUMBER() OVER (PARTITION BY team_id ORDER BY user_id) - 1 AS mix
    FROM team_members
  ),
  spread AS (
    SELECT seq.n           AS n,
           seq.n / 6       AS proj_ix,   -- 0..14, one per active project
           seq.n % 6       AS k,         -- 0..5, the six task archetypes
           ap.id           AS project_id,
           tmn.user_id     AS assignee_id
    FROM seq
    JOIN ap       ON ap.ix = seq.n / 6
    LEFT JOIN tmn ON tmn.team_id = ap.team_id AND tmn.mix = (seq.n % 6) % 4
  )
SELECT
  1000 + s.n,
  s.project_id,
  CASE s.k
    WHEN 0 THEN 'Sửa lỗi pipeline ingest'
    WHEN 1 THEN 'Viết tài liệu API'
    WHEN 2 THEN 'Chuẩn bị slide demo'
    WHEN 3 THEN 'Review code module chính'
    WHEN 4 THEN 'Chạy kiểm thử tích hợp'
    ELSE        'Thiết lập môi trường CI'
  END,
  CASE s.k
    WHEN 0 THEN 'Job ingest fail ở bước chuẩn hoá dữ liệu.'
    WHEN 2 THEN 'Gom kết quả và dựng 6 trang slide.'
    ELSE ''
  END,
  s.assignee_id,   -- round-robin across the owning team's 4 members
  CASE s.k WHEN 0 THEN 'blocked' WHEN 1 THEN 'doing'
           WHEN 5 THEN 'done'    ELSE 'todo' END,
  CASE s.k WHEN 0 THEN 5 WHEN 1 THEN 4 WHEN 2 THEN 5
           WHEN 3 THEN 3 WHEN 4 THEN 2 ELSE 3 END,
  CASE s.k WHEN 0 THEN 40 WHEN 1 THEN 60 WHEN 5 THEN 100 ELSE 0 END,
  CASE s.k
    WHEN 0 THEN datetime('now', '-' || (2 + s.proj_ix % 3) || ' days')
    WHEN 1 THEN datetime('now', '-' || (1 + s.proj_ix % 2) || ' days')
    -- End of today, so this stays "due today" and not also "overdue"
    -- regardless of what time of day the seed is run.
    WHEN 2 THEN datetime('now', 'start of day', '+23 hours', '+59 minutes')
    WHEN 3 THEN datetime('now', '+2 days')
    WHEN 4 THEN datetime('now', '+' || (5 + s.proj_ix % 4) || ' days')
    ELSE        datetime('now', '-' || (7 + s.proj_ix) || ' days')
  END,
  CASE s.k WHEN 0 THEN 'Thiếu quyền truy cập kho dữ liệu nguồn' ELSE '' END,
  CASE s.k WHEN 0 THEN datetime('now', '-' || (3 + s.proj_ix % 4) || ' days') ELSE NULL END
FROM spread s;

-- ------------------------------------------------------------ schedules
-- Daily standups for each team (today + tomorrow), plus programme events.
INSERT OR REPLACE INTO schedules (id, title, event_type, team_id, project_id, starts_at, ends_at, location)
WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM t WHERE n < 5)
SELECT 100 + n, 'Daily stand-up', 'standup', n, NULL,
       datetime('now', 'start of day', '+' || (8 + n) || ' hours'),
       datetime('now', 'start of day', '+' || (8 + n) || ' hours', '+15 minutes'),
       'Discord #t-00' || n
FROM t
UNION ALL
SELECT 200 + n, 'Daily stand-up', 'standup', n, NULL,
       datetime('now', 'start of day', '+1 day', '+' || (8 + n) || ' hours'),
       datetime('now', 'start of day', '+1 day', '+' || (8 + n) || ' hours', '+15 minutes'),
       'Discord #t-00' || n
FROM t;

INSERT OR REPLACE INTO schedules (id, title, event_type, team_id, project_id, starts_at, ends_at, location) VALUES
  (301, 'Mentor review — Team Alpha', 'review',   1, 't001', datetime('now', '+1 day',  '+3 hours'),  datetime('now', '+1 day',  '+4 hours'),  'Zoom room 1'),
  (302, 'Workshop: RAG Pipeline',     'workshop', NULL, NULL, datetime('now', '+2 days', '+6 hours'),  datetime('now', '+2 days', '+8 hours'),  'Hội trường A'),
  (303, 'Gate 2 — hạn nộp',           'deadline', NULL, NULL, datetime('now', '+4 days', '+16 hours'), NULL,                                     'Nộp qua /gate submit'),
  (304, 'Demo Day',                   'demo',     NULL, NULL, datetime('now', '+9 days', '+2 hours'),  datetime('now', '+9 days', '+8 hours'),  'Hội trường chính');

COMMIT;

-- Post-seed assertion. SQLite can only RAISE inside a trigger, so this uses a
-- temp table with a CHECK: if any team is not exactly 4 members the INSERT
-- fails with a constraint error and the script exits non-zero.
CREATE TEMP TABLE _assert (label TEXT, ok TEXT CHECK (ok = 'OK'));
INSERT INTO _assert
SELECT 'teams have exactly 4 members',
       CASE WHEN (SELECT COUNT(*) FROM v_team_integrity) = 0 THEN 'OK' ELSE 'FAIL' END;
INSERT INTO _assert
SELECT 'projects are t001..t100',
       CASE WHEN (SELECT COUNT(*) FROM projects) = 100 THEN 'OK' ELSE 'FAIL' END;
INSERT INTO _assert
SELECT 'every task has a valid project',
       CASE WHEN NOT EXISTS (SELECT 1 FROM tasks t
                              LEFT JOIN projects p ON p.id = t.project_id
                             WHERE p.id IS NULL) THEN 'OK' ELSE 'FAIL' END;
SELECT label || ': ' || ok FROM _assert;
DROP TABLE _assert;
