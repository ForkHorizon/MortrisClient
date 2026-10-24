#!/bin/bash
# Builds the profiling APK: patched SDK copy (V7Prof stages) + probe, IL2CPP development build. Usage: build_prof.sh [arm64|armv7]
set -eu
PR=$(cd "$(dirname "$0")" && pwd); CLIENT=$(cd "$PR/.." && pwd); ARCH=${1:-arm64}
UNITY=${UNITY:-/Applications/Unity/Hub/Editor/6000.3.16f1/Unity.app/Contents/MacOS/Unity}
WORK=$PR/work; mkdir -p "$WORK"
python3 "$PR/patch_sdk.py" "$CLIENT" "$WORK/pkg"
[ -d "$WORK/project/Assets" ] || cp -R "$CLIENT/night-run~/unitywork/project" "$WORK/project"
rm -rf "$WORK/project/Assets/V7Perf" "$WORK/project/Assets/V7Prof" "$WORK/project/Assets/Scenes"
python3 - "$WORK/project/Packages/manifest.json" "$WORK/pkg" <<'PY'
import json, sys
path, pkg = sys.argv[1:3]
m = json.load(open(path)); m['dependencies']['com.daliys.analytics'] = 'file:' + pkg; json.dump(m, open(path, 'w'), indent=2)
PY
mkdir -p "$WORK/project/Assets/V7Prof/Editor"; cp "$PR/unity/V7ProfProbe.cs" "$WORK/project/Assets/V7Prof/"; cp "$PR/unity/V7ProfBuild.cs" "$WORK/project/Assets/V7Prof/Editor/"
EXTRA=""; [ "$ARCH" = armv7 ] && EXTRA="-v7-armv7-only"
"$UNITY" -batchmode -nographics -quit -projectPath "$WORK/project" -buildTarget Android -executeMethod V7ProfBuild.Build -v7-apk "$WORK/v7-prof-$ARCH.apk" $EXTRA -logFile "$WORK/build-$ARCH.log" || { grep -E "error CS|Error" "$WORK/build-$ARCH.log" | head -20; exit 1; }
ls -la "$WORK/v7-prof-$ARCH.apk"
