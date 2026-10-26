#!/bin/bash
# Unity IL2CPP perf probe: real events through the SDK (V7 or V1) against a local server loaded with the real catalog/dictionary.
# Usage: run_unity_perf.sh MODE(v7|v1) N PERFRAME LABEL [SERIAL]   Env: WORK (kept Unity project), APK (prebuilt)
set -eu
NR=$(cd "$(dirname "$0")" && pwd); CLIENT=$(cd "$NR/.." && pwd)
MODE=$1; N=$2; PERFRAME=$3; LABEL=$4; SERIAL=${5:-}
UNITY=${UNITY:-/Applications/Unity/Hub/Editor/6000.3.16f1/Unity.app/Contents/MacOS/Unity}
ADB="$HOME/Library/Android/sdk/platform-tools/adb"; [ -n "$SERIAL" ] && ADB="$ADB -s $SERIAL"
WORK=${WORK:-$NR/unitywork}; mkdir -p "$WORK"; APK=${APK:-$WORK/v7-perf.apk}
OUT=$NR/results/unity/$LABEL; mkdir -p "$OUT"
export MORTRIS_SERVER_REPO=/Users/daliys/Daliys/Web/MortrisServer-v7
. "$CLIENT/Native~/transport-tests/e2e/lib.sh"
trap stack_cleanup EXIT
if [ ! -f "$APK" ]; then
  [ -d "$WORK/project/Assets" ] || "$UNITY" -batchmode -nographics -quit -createProject "$WORK/project" -logFile "$WORK/create.log"
  python3 - "$WORK/project/Packages/manifest.json" "$CLIENT" <<'PY'
import json, sys
path, pkg = sys.argv[1:3]
m = json.load(open(path)); m['dependencies']['com.daliys.analytics'] = 'file:' + pkg; json.dump(m, open(path, 'w'), indent=2)
PY
  mkdir -p "$WORK/project/Assets/V7Perf/Editor"; cp "$NR/unity/V7PerfProbe.cs" "$WORK/project/Assets/V7Perf/"; cp "$NR/unity/V7DeviceBuild.cs" "$WORK/project/Assets/V7Perf/Editor/"
  "$UNITY" -batchmode -nographics -quit -projectPath "$WORK/project" -buildTarget Android -executeMethod V7DeviceBuild.Build -v7-apk "$APK" -logFile "$WORK/build.log" || { tail -40 "$WORK/build.log"; exit 1; }
fi
# server with the real project + catalog + dictionary
start_stack_real() {
  TMP=$(mktemp -d)
  initdb -D "$TMP/data" -U postgres --auth=trust -E UTF8 --locale=en_US.UTF-8 >/dev/null
  pg_ctl -D "$TMP/data" -o "-p $PGPORT -c unix_socket_directories= -c listen_addresses=127.0.0.1 -c fsync=off" -l "$TMP/pg.log" start >/dev/null; sleep 2
  PSQL="psql -h 127.0.0.1 -p $PGPORT -U postgres -v ON_ERROR_STOP=1 -q"
  for r in analytics_migrator analytics_writer analytics_reader analytics_backup analytics_exporter analytics_importer; do $PSQL -c "CREATE ROLE $r LOGIN"; done
  $PSQL -c "CREATE DATABASE mortris_e2e"; DSN="postgres://postgres@127.0.0.1:$PGPORT/mortris_e2e?sslmode=disable"
  (cd "$SERVER_REPO" && go build -o "$TMP/analytics-server" ./cmd/analytics-server)
  export MORTRIS_MIGRATOR_DSN=$DSN MORTRIS_WRITER_DSN=$DSN MORTRIS_READER_DSN=$DSN LISTEN_ADDR=0.0.0.0:$HTTP_PORT
  (cd "$SERVER_REPO" && "$TMP/analytics-server" migrate >/dev/null)
  $PSQL -d mortris_e2e -c "INSERT INTO projects (id, environment, display_name, strict_catalog, enabled) VALUES ('puzzle_gravity_test', 'test', 'puzzle', false, true) ON CONFLICT (id) DO UPDATE SET strict_catalog = false, enabled = true"
  (cd "$SERVER_REPO" && "$TMP/analytics-server" import-transport-assets --project puzzle_gravity_test --catalog "$NR/work/catalog.json" --dictionary "$NR/work/dictionary.bin")
  (cd "$SERVER_REPO" && "$TMP/analytics-server" serve >"$TMP/server.log" 2>&1 &); sleep 2
  SERVER_PID=$(pgrep -f "$TMP/analytics-server serve" | head -1)
  for i in 1 2 3 4 5 6 7 8 9 10; do curl -fsS "http://127.0.0.1:$HTTP_PORT/health/live" >/dev/null 2>&1 && break; sleep 1; done
}
start_stack_real
$ADB install -r "$APK" >/dev/null; $ADB shell pm clear com.daliys.v7perf >/dev/null
DIR=/sdcard/Android/data/com.daliys.v7perf/files; $ADB shell mkdir -p $DIR
printf "mode=$MODE\nn=$N\nperframe=$PERFRAME\n${HOLD:+hold=$HOLD\n}" > "$TMP/config.txt"
$ADB push "$TMP/config.txt" $DIR/config.txt >/dev/null; $ADB push "$NR/work/replay_real_20k.jsonl" $DIR/replay.jsonl >/dev/null
$ADB logcat -c; LOAD0=$(uptime | sed 's/.*averages: //')
$ADB shell am start -n com.daliys.v7perf/com.unity3d.player.UnityPlayerGameActivity >/dev/null
for i in $(seq 1 400); do $ADB logcat -d -s Unity | grep -q "V7PERF result\|V7PERF idle" && break; sleep 3; done
$ADB logcat -d -s Unity > "$OUT/unity-logcat.txt"
grep "V7PERF" "$OUT/unity-logcat.txt" | sed 's/^.*V7PERF/V7PERF/' > "$OUT/perf.txt"; echo "host_load_start=$LOAD0 host_load_end=$(uptime | sed 's/.*averages: //')" >> "$OUT/perf.txt"
Q="psql -h 127.0.0.1 -p $PGPORT -U postgres -d mortris_e2e -tA -c"
echo "db_events=$($Q "SELECT COUNT(*) FROM events WHERE project_id='puzzle_gravity_test'") packets_v2=$(grep -c '"route":"POST /v2/events/packet","status":200' "$TMP/server.log" || true) batches_v1=$(grep -c '"route":"POST /v1/events/batch","status":200' "$TMP/server.log" || true)" >> "$OUT/perf.txt"
cp "$TMP/server.log" "$OUT/server.log"; cat "$OUT/perf.txt"
