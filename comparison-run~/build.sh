#!/bin/bash
# Builds the unified comparison APK (release IL2CPP arm64): unpatched SDK copy + competitor SDKs through bench.CmpAdapter. Usage: build.sh [apk-name]
set -eu
CR=$(cd "$(dirname "$0")" && pwd); CLIENT=$(cd "$CR/.." && pwd); APKNAME=${1:-cmp-arm64.apk}
UNITY=${UNITY:-/Applications/Unity/Hub/Editor/6000.3.16f1/Unity.app/Contents/MacOS/Unity}
WORK=$CR/work; mkdir -p "$WORK"
rsync -a --delete --exclude 'night-run~' --exclude 'profiling-run~' --exclude 'comparison-run~' --exclude 'MortrisV7Data' --exclude 'Theory~' --exclude 'graphify-out' --exclude '.git' --exclude 'Native~' --exclude 'Tests' --exclude 'Samples~' "$CLIENT/" "$WORK/pkg/"
if [ ! -d "$WORK/project/ProjectSettings" ]; then
  mkdir -p "$WORK/project"; "$UNITY" -batchmode -nographics -quit -createProject "$WORK/project" -logFile "$WORK/create.log"
fi
python3 - "$WORK/project/Packages/manifest.json" "$WORK/pkg" <<'PY'
import json, sys
path, pkg = sys.argv[1:3]
m = json.load(open(path)); m['dependencies']['com.daliys.analytics'] = 'file:' + pkg; json.dump(m, open(path, 'w'), indent=2)
PY
A=$WORK/project/Assets; rm -rf "$A/Cmp" "$A/Plugins" "$A/Scenes"; mkdir -p "$A/Cmp/Editor" "$A/Plugins/Android"
cp "$CR/unity/CmpProbe.cs" "$A/Cmp/"; cp "$CR/unity/CmpBuild.cs" "$A/Cmp/Editor/"; cp -R "$CR/unity/plugins/Android/". "$A/Plugins/Android/"
"$UNITY" -batchmode -nographics -quit -projectPath "$WORK/project" -buildTarget Android -executeMethod CmpBuild.Build -v7-apk "$WORK/$APKNAME" -logFile "$WORK/build.log" || { grep -E "error CS|rror:|FAILED|What went wrong" -A3 "$WORK/build.log" | head -60; exit 1; }
ls -la "$WORK/$APKNAME"
