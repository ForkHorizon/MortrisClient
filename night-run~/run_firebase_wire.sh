#!/bin/bash
# Real Firebase Analytics uploads captured on the API 25 emulator (CA in system store, hosts -> 127.0.0.1, adb reverse 443 -> 8443).
cd "$(dirname "$0")"; export PATH=$PATH:$HOME/Library/Android/sdk/platform-tools; S=emulator-5560; M=$PWD/mitm; OUT=$PWD/results/firebase_wire; mkdir -p $OUT
N=${1:-3000}
for rep in 1 2 3; do for mode in prod debug; do
  tag=${mode}_r$rep; [ -f $OUT/$tag.json ] && continue
  pkill -f fbsrv.py; sleep 1; rm -rf $M/fb.log $M/fb.log.bodies; (cd $M && nohup python3 fbsrv.py 8443 $M/fb.log > $M/srv.out 2>&1 &); sleep 1
  adb -s $S reverse tcp:443 tcp:8443 >/dev/null
  [ $mode = debug ] && adb -s $S shell setprop debug.firebase.analytics.app bench.sdk || adb -s $S shell setprop debug.firebase.analytics.app .none.
  adb -s $S shell am force-stop bench.sdk; adb -s $S shell pm clear bench.sdk >/dev/null; adb -s $S shell mkdir -p /sdcard/Android/data/bench.sdk/files
  adb -s $S push $PWD/work/replay_real_20k.jsonl /sdcard/Android/data/bench.sdk/files/replay.jsonl >/dev/null; adb -s $S logcat -c
  G0=$(adb -s $S shell 'for p in $(pidof com.google.android.gms); do cut -d" " -f14,15 /proc/$p/stat; done' | awk '{s+=$1+$2} END {print s}')
  adb -s $S shell am start -n bench.sdk/bench.Main --es sdk firebase --es host 10.0.2.2:1 --ei hz 100 --ei tail 90 --ei n $N >/dev/null
  for i in $(seq 1 100); do sleep 3; adb -s $S logcat -d -s BENCH | grep -q tail_done && break; done
  [ $mode = prod ] && { adb -s $S shell am broadcast -a com.google.android.gms.measurement.UPLOAD -n com.google.android.gms/com.google.android.gms.measurement.PackageMeasurementReceiver >/dev/null; sleep 25; }
  G1=$(adb -s $S shell 'for p in $(pidof com.google.android.gms); do cut -d" " -f14,15 /proc/$p/stat; done' | awk '{s+=$1+$2} END {print s}')
  adb -s $S logcat -d -s BENCH | grep -E "perf2|replay_done" > $OUT/$tag.logcat.txt
  python3 - $tag "$G0" "$G1" $M <<'PY' > $OUT/$tag.json
import json, subprocess, sys
tag, g0, g1, M = sys.argv[1:5]
out = subprocess.run(['python3', M + '/pbcount.py', M + '/fb.log.bodies'], capture_output=True, text=True).stdout.splitlines()[-1]
print(json.dumps({'tag': tag, 'gms_cpu_ticks': int(float(g1)) - int(float(g0)), 'pbcount': out}))
PY
  cat $OUT/$tag.json; echo
done; done
echo done > $OUT/done.txt
