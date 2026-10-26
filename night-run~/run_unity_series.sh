#!/bin/bash
cd "$(dirname "$0")"; export APK=$PWD/unitywork/v7-perf.apk
for rep in 1 2 3; do
  for cfg in "none 2800 20 burst" "v1 2800 20 burst" "v7 2800 20 burst" "none 1200 1 paced" "v1 1200 1 paced" "v7 1200 1 paced"; do
    set -- $cfg
    [ -f results/unity/$1_$4_r$rep/perf.txt ] && grep -q "V7PERF result" results/unity/$1_$4_r$rep/perf.txt && continue
    ./killstale.sh; ./run_unity_perf.sh $1 $2 $3 $1_$4_r$rep emulator-5558 > results/unity_series_last.log 2>&1 || echo "FAILED $cfg $rep"
    echo "$(date +%T) $1 $4 r$rep $(grep -c 'V7PERF result' results/unity/$1_$4_r$rep/perf.txt 2>/dev/null)"
  done
done
echo done > results/unity/series_done.txt
