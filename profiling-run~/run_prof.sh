#!/bin/bash
# One profiling run on a connected device/emulator: fresh local server (real catalog+dictionary), app launch with config, collect V7PROF lines + server stats.
# Usage: run_prof.sh LABEL MODE(v7|v1|none) SCENARIO(single|burst|persec|perframe) "key=val key=val" [SERIAL]
set -eu
PR=$(cd "$(dirname "$0")" && pwd); CLIENT=$(cd "$PR/.." && pwd); NR=$CLIENT/night-run~
LABEL=$1; MODE=$2; SCEN=$3; KV=${4:-}; SERIAL=${5:-}
ADB="$HOME/Library/Android/sdk/platform-tools/adb"; [ -n "$SERIAL" ] && ADB="$ADB -s $SERIAL"
APK=${APK:-$PR/work/v7-prof-arm64.apk}; PKG=com.daliys.v7prof
OUT=$PR/results/${RUNSET:-runs}/$LABEL; mkdir -p "$OUT"
export MORTRIS_SERVER_REPO=${MORTRIS_SERVER_REPO:-/Users/daliys/Daliys/Web/MortrisServer-v7}
. "$CLIENT/Native~/transport-tests/e2e/lib.sh"
trap stack_cleanup EXIT
awk '/^start_stack_real\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$NR/run_unity_phone.sh" > "$PR/work/stack.sh"; . "$PR/work/stack.sh"
start_stack_real
$ADB reverse tcp:18082 tcp:18082 >/dev/null; $ADB install -r "$APK" >/dev/null; $ADB shell pm clear $PKG >/dev/null
DIR=/sdcard/Android/data/$PKG/files; $ADB shell mkdir -p $DIR
{ echo "mode=$MODE"; echo "scenario=$SCEN"; for p in $KV; do echo "$p"; done; } > "$TMP/config.txt"
$ADB push "$TMP/config.txt" $DIR/config.txt >/dev/null; $ADB push "$NR/work/replay_real_20k.jsonl" $DIR/replay.jsonl >/dev/null
$ADB logcat -c; LOAD0=$(uptime | sed 's/.*averages: //')
$ADB shell am start -n $PKG/com.unity3d.player.UnityPlayerGameActivity >/dev/null
for i in $(seq 1 ${WAIT_ITER:-300}); do $ADB logcat -d -s Unity | grep -q "V7PROF done" && break; sleep 3; done
$ADB logcat -d -s Unity > "$OUT/unity-logcat.txt"
grep "V7PROF" "$OUT/unity-logcat.txt" | sed 's/^.*V7PROF //' > "$OUT/prof.txt"
echo "host_load_start=$LOAD0 host_load_end=$(uptime | sed 's/.*averages: //')" >> "$OUT/prof.txt"
Q="psql -h 127.0.0.1 -p $PGPORT -U postgres -d mortris_e2e -tA -c"
echo "db_events=$($Q "SELECT COUNT(*) FROM events WHERE project_id='puzzle_gravity_test'") packets_v2=$(grep -c '"route":"POST /v2/events/packet","status":200' "$TMP/server.log" || true) batches_v1=$(grep -c '"route":"POST /v1/events/batch","status":200' "$TMP/server.log" || true)" >> "$OUT/prof.txt"
cp "$TMP/server.log" "$OUT/server.log"; $ADB shell am force-stop $PKG; grep -E "summary|db_events" "$OUT/prof.txt"
