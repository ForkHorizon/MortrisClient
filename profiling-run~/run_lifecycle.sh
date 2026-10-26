#!/bin/bash
# Lifecycle end-to-end on an emulator/phone: the app tracks one event a second while this script minimises it, lets the session time out, brings it back,
# kills the process (kill -9) and relaunches it; then the server's database is asked which events and session boundaries arrived.
# Usage: CATALOG=<catalog with lifecycle shapes> ./run_lifecycle.sh MODE(v7|v1) [SERIAL]
set -eu
PR=$(cd "$(dirname "$0")" && pwd); CLIENT=$(cd "$PR/.." && pwd); NR=$CLIENT/night-run~
MODE=${1:-v7}; SERIAL=${2:-}
ADB="$HOME/Library/Android/sdk/platform-tools/adb"; [ -n "$SERIAL" ] && ADB="$ADB -s $SERIAL"
APK=${APK:-$PR/work/v7-prof-arm64.apk}; PKG=com.daliys.v7prof; ACT=$PKG/com.unity3d.player.UnityPlayerGameActivity
OUT=$PR/results/lifecycle/$MODE; mkdir -p "$OUT"
export MORTRIS_SERVER_REPO=${MORTRIS_SERVER_REPO:-/Users/daliys/Daliys/Web/MortrisServer-v7}
. "$CLIENT/Native~/transport-tests/e2e/lib.sh"
trap stack_cleanup EXIT
awk '/^start_stack_real\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$NR/run_unity_phone.sh" > "$PR/work/stack.sh"; . "$PR/work/stack.sh"
start_stack_real
q() { psql -h 127.0.0.1 -p $PGPORT -U postgres -d mortris_e2e -tA -F '|' -c "$1"; }
step() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$OUT/steps.txt"; }
: > "$OUT/steps.txt"
$ADB reverse tcp:18082 tcp:18082 >/dev/null; $ADB install -r "$APK" >/dev/null; $ADB shell pm clear $PKG >/dev/null
DIR=/sdcard/Android/data/$PKG/files; $ADB shell mkdir -p $DIR
printf "mode=$MODE\nscenario=forever\nn=100\ntimeout_s=4\nbuffer_ms=200\ninterval_s=${INTERVAL_S:-5}\nbg=${BG:-1}\n" > "$TMP/config.txt"
$ADB push "$TMP/config.txt" $DIR/config.txt >/dev/null; $ADB push "$NR/work/replay_real_20k.jsonl" $DIR/replay.jsonl >/dev/null
$ADB logcat -c
step "launch"; $ADB shell am start -n $ACT >/dev/null; sleep 14
step "background (HOME)"; $ADB shell input keyevent KEYCODE_HOME; sleep 2
step "events durable right after leaving (server has not been told yet unless an upload ran)"; q "SELECT count(*) FROM events" | tee -a "$OUT/steps.txt"
sleep 7
step "return after the session timeout"; $ADB shell am start -n $ACT >/dev/null; sleep 9
step "kill -9 the process"; PID=$($ADB shell pidof $PKG | tr -d '\r'); $ADB shell run-as $PKG kill -9 $PID || $ADB shell kill -9 $PID; sleep 3
step "relaunch"; $ADB shell am start -n $ACT >/dev/null; sleep 16
step "quit cleanly (BACK + force close via am kill is not clean; use the app's own quit path: HOME then wait)"; $ADB shell input keyevent KEYCODE_HOME; sleep 12
q "SELECT name, session_id, occurred_at_client, properties FROM events WHERE name LIKE 'sys\\_%' ORDER BY occurred_at_client, name" > "$OUT/system_events.txt" || true
q "SELECT count(*), count(distinct session_id) FROM events" > "$OUT/totals.txt" || true
$ADB logcat -d -s Unity > "$OUT/unity-logcat.txt"; cp "$TMP/server.log" "$OUT/server.log"
$ADB shell am force-stop $PKG
cat "$OUT/system_events.txt"; echo ---; cat "$OUT/totals.txt"; echo ---; grep -c '"route":"POST /v2/events/packet","status":200' "$TMP/server.log" || true
