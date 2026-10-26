#!/bin/bash
cd "$(dirname "$0")"; S=$(cat START_EPOCH); N=$(date +%s); echo "now $(date +%T)  elapsed $(( (N-S)/60 )) min  remaining $(( (S+28800-N)/60 )) min  load $(uptime | sed 's/.*averages: //')"
echo "--android e1/e2: $(tail -1 results/android_e1.log 2>/dev/null) | $(tail -1 results/android_e2.log 2>/dev/null)"
echo "--fid: $(tail -1 results/android_fid.log 2>/dev/null)   pace2: $(tail -1 results/android_pace2.log 2>/dev/null)"
echo "--unity: $(tail -1 results/unity_series.log 2>/dev/null) ($(ls results/unity 2>/dev/null | wc -l) dirs, done=$(ls results/unity/series_done.txt 2>/dev/null))"
echo "--server: $(tail -1 results/server_series.log 2>/dev/null) done=$(ls results/server/series_done.txt 2>/dev/null)"
echo "--fbwire: $(tail -1 results/firebase_wire.log 2>/dev/null | cut -c1-120) done=$(ls results/firebase_wire/done.txt 2>/dev/null)"
echo "--emulators: $(~/Library/Android/sdk/platform-tools/adb devices | grep -c device$)  procs: $(pgrep -f 'run_android|run_unity|run_server|run_firebase' | wc -l)"
