#!/bin/bash
set -eu
HERE=$(cd "$(dirname "$0")" && pwd); UNITY=/Applications/Unity/Hub/Editor/6000.3.16f1/Unity.app/Contents/MacOS/Unity; WORK=$HERE/unitywork
mkdir -p "$WORK/project/Assets/V7PerfPhone/Editor"; cp "$HERE/unity/V7PerfProbePhone.cs" "$WORK/project/Assets/V7PerfPhone/"; cp "$HERE/unity/V7DeviceBuildPhone.cs" "$WORK/project/Assets/V7PerfPhone/Editor/"
rm -f "$WORK/project/Assets/V7Perf/V7PerfProbe.cs" "$WORK/project/Assets/V7Perf/Editor/V7DeviceBuild.cs" "$WORK/project/Assets/V7Perf/V7PerfProbe.cs.meta" "$WORK/project/Assets/V7Perf/Editor/V7DeviceBuild.cs.meta"
for arch in arm64 armv7; do
  EXTRA=""; [ $arch = armv7 ] && EXTRA="-v7-armv7-only"
  "$UNITY" -batchmode -nographics -quit -projectPath "$WORK/project" -buildTarget Android -executeMethod V7DeviceBuildPhone.Build -v7-apk "$WORK/v7-perf-phone-$arch.apk" $EXTRA -logFile "$WORK/build-phone-$arch.log" || { tail -30 "$WORK/build-phone-$arch.log"; exit 1; }
  ls -la "$WORK/v7-perf-phone-$arch.apk"
done
