# Shared by run-e2e.sh and run-device.sh: starts a throwaway PostgreSQL and the server from the feat/v7-transport worktree.
# Sets TMP, PSQL, HTTP_PORT and SERVER_PID; call stack_cleanup (usually from a trap).
SERVER_REPO=${MORTRIS_SERVER_REPO:-/Users/daliys/Daliys/Web/MortrisServer-v7}
HERE=$(cd "$(dirname "$0")/.." && pwd)
PGPORT=${PGPORT:-54331}; HTTP_PORT=${HTTP_PORT:-18081}
export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
stack_cleanup() {
  [ -n "${SERVER_PID:-}" ] && kill "$SERVER_PID" 2>/dev/null || true
  if [ -n "${TMP:-}" ]; then pg_ctl -D "$TMP/data" stop -m fast >/dev/null 2>&1 || true; rm -rf "$TMP"; fi
}
start_stack() {
  TMP=$(mktemp -d)
  initdb -D "$TMP/data" -U postgres --auth=trust -E UTF8 --locale=en_US.UTF-8 >/dev/null
  pg_ctl -D "$TMP/data" -o "-p $PGPORT -c unix_socket_directories= -c listen_addresses=127.0.0.1 -c fsync=off" -l "$TMP/pg.log" start >/dev/null
  sleep 2
  PSQL="psql -h 127.0.0.1 -p $PGPORT -U postgres -v ON_ERROR_STOP=1 -q"
  for r in analytics_migrator analytics_writer analytics_reader analytics_backup analytics_exporter analytics_importer; do $PSQL -c "CREATE ROLE $r LOGIN"; done
  $PSQL -c "CREATE DATABASE mortris_e2e"
  DSN="postgres://postgres@127.0.0.1:$PGPORT/mortris_e2e?sslmode=disable"
  (cd "$SERVER_REPO" && go build -o "$TMP/analytics-server" ./cmd/analytics-server)
  export MORTRIS_MIGRATOR_DSN=$DSN MORTRIS_WRITER_DSN=$DSN MORTRIS_READER_DSN=$DSN LISTEN_ADDR=127.0.0.1:$HTTP_PORT
  (cd "$SERVER_REPO" && "$TMP/analytics-server" migrate >/dev/null)
  $PSQL -d mortris_e2e -c "INSERT INTO projects (id, environment, display_name, strict_catalog, enabled) VALUES ('synth_indie_runner', 'test', 'synth', false, true)"
  [ "${M7_SKIP_ASSETS:-0}" = 1 ] || (cd "$SERVER_REPO" && "$TMP/analytics-server" import-transport-assets --project synth_indie_runner --catalog "$HERE/fixtures/catalog-plain.json" --dictionary "$HERE/fixtures/dictionary-plain.bin")
  (cd "$SERVER_REPO" && "$TMP/analytics-server" serve >"$TMP/server.log" 2>&1 &); sleep 2
  SERVER_PID=$(pgrep -f "$TMP/analytics-server serve" | head -1)
  for i in 1 2 3 4 5 6 7 8 9 10; do curl -fsS "http://127.0.0.1:$HTTP_PORT/health/live" >/dev/null 2>&1 && break; sleep 1; done
  curl -fsS "http://127.0.0.1:$HTTP_PORT/health/live" >/dev/null
}
