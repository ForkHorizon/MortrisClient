#!/bin/bash
cd "$(dirname "$0")"; export PATH=$PATH:$HOME/Library/Android/sdk/platform-tools; S=0006814AG001387; L=results/phone_driver.log; log() { echo "$(date +%T) $*" | tee -a $L; }
while pgrep -f "run_android.py $S" >/dev/null; do sleep 20; done; log "android matrix done; Unity arm64 series"
mkdir -p results/unity_phone
for rep in 1 2 3; do
  for cfg in "none 2800 20 burst" "v1 2800 20 burst" "v7 2800 20 burst" "none 1200 1 paced" "v1 1200 1 paced" "v7 1200 1 paced"; do
    set -- $cfg; tag=$1_$4_r$rep
    grep -q "V7PERF result" results/unity_phone/$tag/perf.txt 2>/dev/null && continue
    ./killstale.sh; APK=$PWD/unitywork/v7-perf-phone-arm64.apk ./run_unity_phone.sh $1 $2 $3 $tag $S > results/unity_phone_last.log 2>&1 || log "FAILED $tag"
    log "$tag $(grep -c 'V7PERF result' results/unity_phone/$tag/perf.txt 2>/dev/null)"
  done
done
log "idle phone runs"
for mode in none v1 v7; do ./killstale.sh; HOLD=60 APK=$PWD/unitywork/v7-perf-phone-arm64.apk ./run_unity_phone.sh $mode 100 20 idle_$mode $S > /dev/null 2>&1; grep -h "V7PERF idle" results/unity_phone/idle_$mode/unity-logcat.txt | sed 's/^.*V7PERF/V7PERF/' | tee -a $L; done
log "ARMv7 attempt"
./killstale.sh; APK=$PWD/unitywork/v7-perf-phone-armv7.apk ./run_unity_phone.sh v7 1200 20 armv7_v7_burst $S > results/unity_phone_armv7.log 2>&1 || log "ARMv7 run failed"
adb -s $S logcat -d | grep -iE "armv7|armeabi|UnsatisfiedLink|dlopen failed|libdaliys_zstd|INSTALL_FAILED|FATAL EXCEPTION" | tail -5 | tee -a $L
log "restore phone settings"
adb -s $S shell "svc wifi enable; svc data enable; svc power stayon false"; adb -s $S reverse --remove-all
log "PHONE ALL DONE"; echo done > results/phone_done.txt
