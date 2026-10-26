#!/bin/bash
# Server-side cost of ingesting the same real events through V1 or V7: CPU/RSS of the Go server and PostgreSQL, throughput.
# Usage: run_server_load.sh MODE(v1|v7) LABEL [INSTALLS] [EVENTS] [PARALLEL]
set -eu
NR=$(cd "$(dirname "$0")" && pwd); CLIENT=$(cd "$NR/.." && pwd)
MODE=$1; LABEL=$2; INSTALLS=${3:-24}; EVENTS=${4:-60000}; PAR=${5:-4}
OUT=$NR/results/server/$LABEL; mkdir -p "$OUT"
export MORTRIS_SERVER_REPO=/Users/daliys/Daliys/Web/MortrisServer-v7
. "$CLIENT/Native~/transport-tests/e2e/lib.sh"
trap stack_cleanup EXIT
TMP=$(mktemp -d); initdb -D "$TMP/data" -U postgres --auth=trust -E UTF8 --locale=en_US.UTF-8 >/dev/null
pg_ctl -D "$TMP/data" -o "-p $PGPORT -c unix_socket_directories= -c listen_addresses=127.0.0.1 -c fsync=off" -l "$TMP/pg.log" start >/dev/null; sleep 2
PSQL="psql -h 127.0.0.1 -p $PGPORT -U postgres -v ON_ERROR_STOP=1 -q"
for r in analytics_migrator analytics_writer analytics_reader analytics_backup analytics_exporter analytics_importer; do $PSQL -c "CREATE ROLE $r LOGIN"; done
$PSQL -c "CREATE DATABASE mortris_e2e"; DSN="postgres://postgres@127.0.0.1:$PGPORT/mortris_e2e?sslmode=disable"
(cd "$SERVER_REPO" && go build -o "$TMP/analytics-server" ./cmd/analytics-server)
export MORTRIS_MIGRATOR_DSN=$DSN MORTRIS_WRITER_DSN=$DSN MORTRIS_READER_DSN=$DSN LISTEN_ADDR=127.0.0.1:$HTTP_PORT
(cd "$SERVER_REPO" && "$TMP/analytics-server" migrate >/dev/null)
$PSQL -d mortris_e2e -c "INSERT INTO projects (id, environment, display_name, strict_catalog, enabled) VALUES ('puzzle_gravity_test', 'test', 'puzzle', false, true) ON CONFLICT (id) DO UPDATE SET strict_catalog = false, enabled = true"
(cd "$SERVER_REPO" && "$TMP/analytics-server" import-transport-assets --project puzzle_gravity_test --catalog "$NR/work/catalog.json" --dictionary "$NR/work/dictionary.bin" >/dev/null)
(cd "$SERVER_REPO" && "$TMP/analytics-server" serve >"$TMP/server.log" 2>&1 &); sleep 2
SPID=$(pgrep -f "$TMP/analytics-server serve" | head -1); SERVER_PID=$SPID
for i in 1 2 3 4 5 6 7 8 9 10; do curl -fsS "http://127.0.0.1:$HTTP_PORT/health/live" >/dev/null 2>&1 && break; sleep 1; done
cpu() { ps -o cputime= -p "$1" 2>/dev/null | awk -F'[:.]' '{ if (NF==3) print $1*60+$2+$3/100; else print $1*3600+$2*60+$3+$4/100 }'; }
pgpids() { PM=$(head -1 "$TMP/data/postmaster.pid"); echo $PM $(pgrep -P $PM); }
pgcpu() { for p in $(pgpids); do cpu $p; done | awk '{s+=$1} END {print s+0}'; }
rss() { for p in "$@"; do ps -o rss= -p $p 2>/dev/null; done | awk '{s+=$1} END {print s/1024}'; }
S0=$(cpu $SPID); P0=$(pgcpu); LOAD0=$(uptime | sed 's/.*averages: //')
export DALIYS_ZSTD="$CLIENT/Runtime/Plugins/macOS/libdaliys_zstd.dylib"
# peak RSS sampler
( peak=0; while kill -0 $SPID 2>/dev/null; do r=$(rss $SPID); pr=$(rss $(pgpids)); echo "$r $pr" >> "$OUT/rss.samples"; sleep 0.5; done ) >/dev/null 2>&1 &
SAMP=$!
dotnet "$NR/loadgen/bin/Release/net10.0/LoadGen.dll" $MODE "http://127.0.0.1:$HTTP_PORT" "$NR/work/batches.jsonl" $INSTALLS $EVENTS $PAR "$OUT/loadgen.json" || echo "loadgen failed: $(cat $OUT/loadgen.json 2>/dev/null)"
S1=$(cpu $SPID); P1=$(pgcpu)
EV=$($PSQL -d mortris_e2e -tA -c "SELECT COUNT(*) FROM events WHERE project_id='puzzle_gravity_test'")
BYTES=$(grep -c . "$TMP/server.log" || true)
cp "$TMP/server.log" "$OUT/server.log"; cp "$TMP/pg.log" "$OUT/pg.log"; kill $SAMP 2>/dev/null || true
python3 - "$OUT" "$S0" "$S1" "$P0" "$P1" "$EV" "$LOAD0" <<'PY'
import json, sys
out, s0, s1, p0, p1, ev, load0 = sys.argv[1:8]
lg = json.load(open(out + '/loadgen.json')); ev = int(ev); rs = [tuple(map(float, l.split())) for l in open(out + '/rss.samples') if len(l.split()) == 2] or [(0, 0)]
res = dict(lg, db_events=ev, server_cpu_s=float(s1) - float(s0), postgres_cpu_s=float(p1) - float(p0),
           server_cpu_us_per_event=(float(s1) - float(s0)) * 1e6 / max(ev, 1), postgres_cpu_us_per_event=(float(p1) - float(p0)) * 1e6 / max(ev, 1),
           server_rss_peak_mb=max(r[0] for r in rs), postgres_rss_peak_mb=max(r[1] for r in rs), events_per_s=ev / max(lg['wall_s'], 0.001), host_load_start=load0)
json.dump(res, open(out + '/result.json', 'w'), indent=1); print(json.dumps(res))
PY
