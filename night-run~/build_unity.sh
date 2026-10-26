#!/bin/bash
set -eu
HERE=$(cd "$(dirname "$0")" && pwd); CLIENT=$(cd "$HERE/.." && pwd); UNITY=/Applications/Unity/Hub/Editor/6000.3.16f1/Unity.app/Contents/MacOS/Unity
WORK=$HERE/unitywork; mkdir -p $WORK; APK=$WORK/v7-perf.apk
[ -d "$WORK/project/Assets" ] || "$UNITY" -batchmode -nographics -quit -createProject "$WORK/project" -logFile "$WORK/create.log"
python3 - "$WORK/project/Packages/manifest.json" "$CLIENT" <<'PY'
import json, sys
path, pkg = sys.argv[1:3]
m = json.load(open(path)); m['dependencies']['com.daliys.analytics'] = 'file:' + pkg; json.dump(m, open(path, 'w'), indent=2)
PY
mkdir -p "$WORK/project/Assets/V7Perf/Editor"; cp "$HERE/unity/V7PerfProbe.cs" "$WORK/project/Assets/V7Perf/"; cp "$HERE/unity/V7DeviceBuild.cs" "$WORK/project/Assets/V7Perf/Editor/"
rm -f "$APK"; "$UNITY" -batchmode -nographics -quit -projectPath "$WORK/project" -buildTarget Android -executeMethod V7DeviceBuild.Build -v7-apk "$APK" -logFile "$WORK/build.log" || { tail -40 "$WORK/build.log"; exit 1; }
ls -la "$APK"; echo BUILD_OK
