#!/bin/bash
cd "$(dirname "$0")"; export APK=$PWD/unitywork/v7-perf.apk
for rep in 1 2; do for mode in v1 v7; do ./killstale.sh; ./run_unity_perf.sh $mode 1200 1 thr_${mode}_r$rep emulator-5558 >/dev/null 2>&1; echo "$mode r$rep: $(grep -h 'V7PERF threads' results/unity/thr_${mode}_r$rep/perf.txt | cut -c1-430)"; done; done
