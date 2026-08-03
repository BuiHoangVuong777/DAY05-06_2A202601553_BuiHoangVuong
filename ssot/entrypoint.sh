#!/bin/sh
# Initialise the DB on first run, then serve the web UI.
#   FORCE_RESEED=1  -> delete and rebuild the DB even if it already exists
set -e

DB="${DB_PATH:-/data/ssot.db}"
mkdir -p "$(dirname "$DB")"

if [ "${FORCE_RESEED:-0}" = "1" ]; then
  echo "[ssot] FORCE_RESEED=1 — removing $DB"
  rm -f "$DB" "$DB-wal" "$DB-shm"
fi

if [ ! -f "$DB" ]; then
  echo "[ssot] initialising $DB"
  sqlite3 "$DB" < /sql/schema.sql
  sqlite3 "$DB" < /sql/seed.sql
  echo "[ssot] seeded: $(sqlite3 "$DB" 'SELECT COUNT(*) FROM projects') projects, \
$(sqlite3 "$DB" 'SELECT COUNT(*) FROM tasks') tasks, \
$(sqlite3 "$DB" 'SELECT COUNT(*) FROM users') users"
else
  echo "[ssot] reusing existing $DB (set FORCE_RESEED=1 to rebuild)"
fi

# Fail fast if the data is not in the shape the demo expects.
BAD=$(sqlite3 "$DB" "SELECT COUNT(*) FROM v_team_integrity")
if [ "$BAD" != "0" ]; then
  echo "[ssot] FATAL: $BAD team(s) do not have exactly 4 members" >&2
  exit 1
fi
echo "[ssot] integrity OK — all teams have exactly 4 members"

# No args -> serve the web UI. Any args -> run them instead (e.g. `sqlite3 $DB`).
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

echo "[ssot] sqlite-web on :8080"
exec sqlite_web --host 0.0.0.0 --port 8080 --no-browser "$DB"
