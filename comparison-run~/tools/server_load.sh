#!/bin/bash
# Server-side load with N parallel installs through V1 / V7 / V8 (same real holdout events, 100-event batches, 20 batches per install). Usage: server_load.sh MODE LABEL INSTALLS
# Fresh PostgreSQL + V8-server per run; CPU seconds of server and PostgreSQL, peak RSS, wall time, errors (429 etc.).
set -eu
CR=$(cd "$(dirname "$0")/.." && pwd); NR=$CR/../night-run~; MODE=$1; LABEL=$2; INSTALLS=$3; OUT=$CR/results/server/$LABEL; mkdir -p "$OUT"
PG=54430; HP=18130; KEEP=1
"$CR/tools/stack_start.sh" load_$LABEL $PG $HP seed-v7 >/dev/null
. "$CR/work/stacks/load_$LABEL.env"
cpu() { ps -o cputime= -p "$1" 2>/dev/null | awk -F'[:.]' '{ if (NF==3) print $1*60+$2+$3/100; else print $1*3600+$2*60+$3+$4/100 }'; }
pgpids() { PM=$(head -1 "$TMP/data/postmaster.pid"); echo $PM $(pgrep -P $PM); }
pgcpu() { for p in $(pgpids); do cpu $p; done | awk '{s+=$1} END {print s+0}'; }
rss() { for p in "$@"; do ps -o rss= -p $p 2>/dev/null; done | awk '{s+=$1} END {print s/1024}'; }
S0=$(cpu $SERVER_PID); P0=$(pgcpu); LOAD0=$(uptime | sed 's/.*averages: //')
( while kill -0 $SERVER_PID 2>/dev/null; do echo "$(rss $SERVER_PID) $(rss $(pgpids))" >> "$OUT/rss.samples"; sleep 0.5; done ) >/dev/null 2>&1 &
SAMP=$!
export DALIYS_ZSTD="$CR/../Runtime/Plugins/macOS/libdaliys_zstd.dylib" LOADGEN_RPS=${LOADGEN_RPS:-25}
set +e; dotnet "$CR/loadgen/bin/Release/net10.0/LoadGen.dll" $MODE "http://127.0.0.1:$HP" "$NR/work/lc_holdout_b100.jsonl" $INSTALLS $((INSTALLS*2000)) ${LOADGEN_PAR:-$INSTALLS} "$OUT/loadgen.json"; RC=$?; set -e
S1=$(cpu $SERVER_PID); P1=$(pgcpu)
EV=$(psql -h 127.0.0.1 -p $PG -U postgres -d mortris_cmp -tA -c "SELECT COUNT(*) FROM events WHERE project_id='puzzle_gravity_test'")
cp "$TMP/server.log" "$OUT/server.log"; kill $SAMP 2>/dev/null || true
python3 - "$OUT" "$S0" "$S1" "$P0" "$P1" "$EV" "$LOAD0" "$RC" <<'PY'
import json, sys
out, s0, s1, p0, p1, ev, load0, rc = sys.argv[1:9]
rss = [tuple(map(float, l.split())) for l in open(out + '/rss.samples') if l.strip()]
lg = {}
try: lg = json.load(open(out + '/loadgen.json'))
except Exception: pass
d = dict(loadgen=lg, rc=int(rc), server_cpu_s=float(s1) - float(s0), pg_cpu_s=float(p1) - float(p0), db_events=int(ev), server_rss_peak_mb=max([r[0] for r in rss] or [0]), pg_rss_peak_mb=max([r[1] for r in rss] or [0]), load_start=load0)
d['server_cpu_us_per_event'] = d['server_cpu_s'] * 1e6 / max(d['db_events'], 1); d['pg_cpu_us_per_event'] = d['pg_cpu_s'] * 1e6 / max(d['db_events'], 1)
json.dump(d, open(out + '/result.json', 'w'), indent=1); print(json.dumps(d))
PY
grep -c '"status":429' "$OUT/server.log" | sed 's/^/http429=/' >> "$OUT/result.txt" || true
"$CR/tools/stack_stop.sh" load_$LABEL
