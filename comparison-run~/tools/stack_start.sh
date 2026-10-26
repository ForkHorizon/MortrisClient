#!/bin/bash
# Throwaway PostgreSQL + Mortris server (V8 worktree: serves /v1, /v2 and /v3). Usage: stack_start.sh LABEL PGPORT HTTPPORT [seed-v7]
# Writes work/stacks/LABEL.env (TMP, SERVER_PID, PGPORT, HTTPPORT). seed-v7 imports the catalog+dictionary trained on the TRAIN installs only.
set -eu
CR=$(cd "$(dirname "$0")/.." && pwd); NR=$CR/../night-run~
LABEL=$1; PGPORT=$2; HTTPPORT=$3; SEED=${4:-}
SERVER_REPO=${MORTRIS_SERVER_REPO:-/Users/daliys/Daliys/Web/MortrisServer-v8}
export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
mkdir -p "$CR/work/stacks"; TMP=$(mktemp -d "$CR/work/stacks/$LABEL.XXXX")
initdb -D "$TMP/data" -U postgres --auth=trust -E UTF8 --locale=en_US.UTF-8 >/dev/null
pg_ctl -D "$TMP/data" -o "-p $PGPORT -c unix_socket_directories= -c listen_addresses=127.0.0.1 -c fsync=off -c max_connections=200" -l "$TMP/pg.log" start >/dev/null; sleep 2
PSQL="psql -h 127.0.0.1 -p $PGPORT -U postgres -v ON_ERROR_STOP=1 -q"
for r in analytics_migrator analytics_writer analytics_reader analytics_backup analytics_exporter analytics_importer; do $PSQL -c "CREATE ROLE $r LOGIN"; done
$PSQL -c "CREATE DATABASE mortris_cmp"; DSN="postgres://postgres@127.0.0.1:$PGPORT/mortris_cmp?sslmode=disable"
BIN=$CR/work/analytics-server-v8; (cd "$SERVER_REPO" && go build -o "$BIN" ./cmd/analytics-server)
export MORTRIS_MIGRATOR_DSN=$DSN MORTRIS_WRITER_DSN=$DSN MORTRIS_READER_DSN=$DSN LISTEN_ADDR=0.0.0.0:$HTTPPORT
export MORTRIS_TRANSPORT_MASTER_KEYS=${MORTRIS_TRANSPORT_MASTER_KEYS:-k:0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f20}
(cd "$SERVER_REPO" && "$BIN" migrate >/dev/null)
$PSQL -d mortris_cmp -c "INSERT INTO projects (id, environment, display_name, strict_catalog, enabled) VALUES ('puzzle_gravity_test', 'test', 'puzzle', false, true) ON CONFLICT (id) DO UPDATE SET strict_catalog = false, enabled = true"
for P in casual_test midcore_test telemetry_test; do $PSQL -d mortris_cmp -c "INSERT INTO projects (id, environment, display_name, strict_catalog, enabled) VALUES ('$P', 'test', '$P', false, true) ON CONFLICT (id) DO UPDATE SET strict_catalog = false, enabled = true"; done
if [ "$SEED" = seed-v7 ]; then (cd "$SERVER_REPO" && "$BIN" import-transport-assets --project puzzle_gravity_test --catalog "${CATALOG:-$NR/work/catalog.json}" --dictionary "${DICT:-$NR/work/dictionary.bin}" >/dev/null); fi
(cd "$SERVER_REPO" && "$BIN" serve >"$TMP/server.log" 2>&1 & echo $! > "$TMP/pid"); sleep 2
SERVER_PID=$(lsof -ti tcp:$HTTPPORT -sTCP:LISTEN | head -1)
for i in 1 2 3 4 5 6 7 8 9 10; do curl -fsS "http://127.0.0.1:$HTTPPORT/health/live" >/dev/null 2>&1 && break; sleep 1; done
curl -fsS "http://127.0.0.1:$HTTPPORT/health/live" >/dev/null
printf "TMP=%s\nSERVER_PID=%s\nPGPORT=%s\nHTTPPORT=%s\n" "$TMP" "$SERVER_PID" "$PGPORT" "$HTTPPORT" > "$CR/work/stacks/$LABEL.env"; echo "stack $LABEL up on $HTTPPORT"
