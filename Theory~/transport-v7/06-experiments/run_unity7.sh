#!/bin/sh
set -eu
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
PY=${PY:-../../transport-v3/06-experiments/.venv/bin/python}
UNITY=/Applications/Unity/Hub/Editor/6000.3.16f1/Unity.app/Contents/MacOS/Unity
TASK_ROOT=$(pwd)
"$PY" prepare_unity7.py > results/unity-prepare.log
"$UNITY" -batchmode -nographics -projectPath "$TASK_ROOT/results/private/unity-player" -executeMethod TransportV7Research.EditorBootstrap.ReportEnvironment --v7-output "$TASK_ROOT/results/unity-module-before.json" -logFile "$TASK_ROOT/results/unity-environment.log"
"$PY" prepare_android7.py > results/android-native-build.log 2>&1
"$UNITY" -batchmode -nographics -buildTarget Android -projectPath "$TASK_ROOT/results/private/unity-player" -executeMethod TransportV7Research.EditorBootstrap.BuildAndroid --v7-development --v7-player "$TASK_ROOT/results/private/transport-v7-development.apk" -logFile "$TASK_ROOT/results/unity-android-build.log"
"$PY" run_android7.py > results/android-run.log 2>&1
"$PY" run_android7.py --serial emulator-5554 --avd Pixel_8 --name unity-android-16k > results/android-16k-run.log 2>&1
"$UNITY" -batchmode -nographics -projectPath "$TASK_ROOT/results/private/unity-player" -executeMethod TransportV7Research.EditorBootstrap.RunEditor --v7-output "$TASK_ROOT/results/private/unity-editor-output" -logFile "$TASK_ROOT/results/unity-editor.log"
"$PY" verify_unity7.py
"$PY" export_reports7.py
"$PY" verify7.py
"$PY" snapshot.py
"$PY" freeze7.py
