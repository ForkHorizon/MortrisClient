#!/bin/sh
# Device proof: builds an isolated Unity project (IL2CPP, ARM64+ARMv7) that uses this package, runs it on an Android emulator against a local
# MortrisServer + PostgreSQL, and checks the database: V7 packets stored, a V1 fallback event stored, no gaps in the sequence stream.
# Usage: run-device.sh [path-to-prebuilt.apk]   (set V7_DEVICE_WORK to keep the Unity project between runs)
# SCENARIO=normal (default) | nocatalog (project without V7 assets: everything must go through V1) | kill (app is killed mid-run and restarted)
set -eu
. "$(dirname "$0")/lib.sh"
UNITY=${UNITY:-/Applications/Unity/Hub/Editor/6000.3.16f1/Unity.app/Contents/MacOS/Unity}
ADB=${ADB:-$HOME/Library/Android/sdk/platform-tools/adb}
PKG=$(cd "$HERE/../.." && pwd)
WORK=${V7_DEVICE_WORK:-$(mktemp -d)}; mkdir -p "$WORK"
APK=${1:-$WORK/v7-device.apk}
trap stack_cleanup EXIT

if [ ! -f "$APK" ]; then
  if [ ! -d "$WORK/project/Assets" ]; then "$UNITY" -batchmode -nographics -quit -createProject "$WORK/project" -logFile "$WORK/create.log"; fi
  python3 - "$WORK/project/Packages/manifest.json" "$PKG" <<'PY'
import json, sys
path, pkg = sys.argv[1:3]
manifest = json.load(open(path)); manifest['dependencies']['com.daliys.analytics'] = 'file:' + pkg
json.dump(manifest, open(path, 'w'), indent=2)
PY
  mkdir -p "$WORK/project/Assets/V7Device/Editor"
  cp "$HERE/device/V7DeviceProbe.cs" "$WORK/project/Assets/V7Device/"
  cp "$HERE/device/V7DeviceBuild.cs" "$WORK/project/Assets/V7Device/Editor/"
  "$UNITY" -batchmode -nographics -quit -projectPath "$WORK/project" -buildTarget Android -executeMethod V7DeviceBuild.Build -v7-apk "$APK" -logFile "$WORK/build.log" || { tail -40 "$WORK/build.log"; exit 1; }
fi
[ -f "$APK" ]
"$ADB" devices | grep -q "device$" || { echo "no Android emulator/device is connected"; exit 1; }
SCENARIO=${SCENARIO:-normal}
[ "$SCENARIO" = nocatalog ] && M7_SKIP_ASSETS=1
start_stack
"$ADB" install -r "$APK" >/dev/null
"$ADB" shell pm clear com.daliys.v7device >/dev/null
"$ADB" logcat -c
LAUNCH() { "$ADB" shell am start -n com.daliys.v7device/com.unity3d.player.UnityPlayerGameActivity >/dev/null; }
LAUNCH
if [ "$SCENARIO" = kill ]; then
  sleep 5; "$ADB" shell am force-stop com.daliys.v7device    # mid-run: events still in the in-memory handoff are lost, queued ones must survive
  sleep 2; "$ADB" logcat -c; LAUNCH
fi
DONE=0
for i in $(seq 1 90); do
  if "$ADB" logcat -d -s Unity | grep -q "V7DEVICE finished"; then DONE=1; break; fi
  sleep 3
done
"$ADB" logcat -d -s Unity > "$WORK/unity-logcat.txt"; "$ADB" logcat -d > "$WORK/full-logcat.txt"
grep "V7DEVICE" "$WORK/unity-logcat.txt" | sed 's/^.*V7DEVICE/V7DEVICE/' || true
[ "$DONE" = 1 ] || { echo "the app did not finish"; exit 1; }
if grep -E "FATAL EXCEPTION|DllNotFound|EntryPointNotFound" "$WORK/full-logcat.txt" | grep -q .; then echo "device log shows a crash or a missing native library"; grep -E "FATAL EXCEPTION|DllNotFound|EntryPointNotFound" "$WORK/full-logcat.txt" | head; exit 1; fi

Q="psql -h 127.0.0.1 -p $PGPORT -U postgres -d mortris_e2e -tA -c"
EVENTS=$($Q "SELECT COUNT(*) FROM events WHERE project_id = 'synth_indie_runner'")
SEQ=$($Q "SELECT COUNT(DISTINCT sequence) || ',' || MIN(sequence) || ',' || MAX(sequence) FROM events WHERE project_id = 'synth_indie_runner'")
UNKNOWN=$($Q "SELECT COUNT(*) FROM events WHERE project_id = 'synth_indie_runner' AND properties ? 'mystery'")
STREAMS=$($Q "SELECT COUNT(*) FROM transport_streams WHERE project_id = 'synth_indie_runner'")
PACKETS=$(grep -c '"route":"POST /v2/events/packet","status":200' "$TMP/server.log" || true)
V1BATCHES=$(grep -c '"route":"POST /v1/events/batch","status":200' "$TMP/server.log" || true)
ACK=$($Q "SELECT high_water || ' ' || received::text FROM transport_streams WHERE project_id = 'synth_indie_runner' ORDER BY epoch DESC LIMIT 1")
echo "events=$EVENTS sequences(distinct,min,max)=$SEQ unknown_shape_events=$UNKNOWN streams=$STREAMS v2_packets=$PACKETS v1_batches=$V1BATCHES stream_state='$ACK'"
FAIL=0
if [ "$SCENARIO" = normal ]; then
  [ "$EVENTS" = 121 ] || { echo "FAIL: expected 121 events"; FAIL=1; }
  [ "$SEQ" = "121,1,121" ] || { echo "FAIL: sequences are not exactly 1..121"; FAIL=1; }
  [ "$UNKNOWN" = 1 ] || { echo "FAIL: the unknown-shape event did not arrive"; FAIL=1; }
  [ "$STREAMS" -ge 1 ] || { echo "FAIL: no V7 stream was opened"; FAIL=1; }
  [ "$PACKETS" -ge 1 ] || { echo "FAIL: no V7 packet was accepted"; FAIL=1; }
  [ "$V1BATCHES" -ge 1 ] || { echo "FAIL: the V1 fallback never ran"; FAIL=1; }
elif [ "$SCENARIO" = nocatalog ]; then
  [ "$EVENTS" = 121 ] || { echo "FAIL: expected 121 events through V1"; FAIL=1; }
  [ "$PACKETS" = 0 ] || { echo "FAIL: V7 packets were sent although the project has no catalog"; FAIL=1; }
  [ "$V1BATCHES" -ge 1 ] || { echo "FAIL: V1 never ran"; FAIL=1; }
else
  DISTINCT=$(echo "$SEQ" | cut -d, -f1); MIN=$(echo "$SEQ" | cut -d, -f2); MAX=$(echo "$SEQ" | cut -d, -f3)
  [ "$EVENTS" = "$DISTINCT" ] || { echo "FAIL: duplicate sequence numbers stored"; FAIL=1; }
  [ "$MIN" = 1 ] && [ "$MAX" = "$DISTINCT" ] || { echo "FAIL: the sequence has gaps ($SEQ)"; FAIL=1; }
  [ "$EVENTS" -ge 121 ] || { echo "FAIL: fewer events than the restarted run alone should deliver"; FAIL=1; }
  [ "$PACKETS" -ge 1 ] || { echo "FAIL: no V7 packet was accepted"; FAIL=1; }
fi
[ "$FAIL" = 0 ] && echo "DEVICE PROOF PASSED ($SCENARIO)" || { echo "server log tail:"; tail -5 "$TMP/server.log"; exit 1; }
