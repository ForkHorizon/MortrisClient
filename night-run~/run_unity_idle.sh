#!/bin/bash
cd "$(dirname "$0")"; export APK=$PWD/unitywork/v7-perf.apk; mkdir -p results/unity_idle
sed_cfg() { :; }
for rep in 1 2 3; do for mode in none v1 v7; do
  tag=idle_${mode}_r$rep; [ -s results/unity_idle/$tag.txt ] && continue
  # run_unity_perf.sh writes config "mode,n,perframe"; add the hold key through a wrapper env
  HOLD=60 ./run_unity_perf.sh $mode 100 20 $tag emulator-5558 > /dev/null 2>&1
  grep -h "V7PERF idle" results/unity/$tag/unity-logcat.txt | sed 's/^.*V7PERF/V7PERF/' > results/unity_idle/$tag.txt; cat results/unity_idle/$tag.txt
done; done
echo done > results/unity_idle/done.txt
