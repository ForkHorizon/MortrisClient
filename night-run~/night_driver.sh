#!/bin/bash
# Unattended clean phase: runs the measurement jobs one after another (nothing else on the host except the user's own apps).
cd "$(dirname "$0")"; export PATH=$PATH:$HOME/Library/Android/sdk/platform-tools; L=results/driver.log; log() { echo "$(date +%T) $*" | tee -a $L; }
log "driver waiting for C1"; while pgrep -f "run_android.py emulator-5554 18471 c1" >/dev/null; do sleep 20; done
log "C1 done; firebase prod-mode rerun (c1b)"
python3 run_android.py emulator-5554 18472 c1b 3 6000 0 firebase > results/android_c1b.log 2>&1
log "C2 on API25 (5560) with sinks"
pkill -f fbsrv.py; sleep 1; rm -rf mitm/fb.log mitm/fb.log.*; (cd mitm && nohup python3 fbsrv.py 8443 $PWD/fb.log > srv.out 2>&1 &); sleep 1; adb -s emulator-5560 reverse tcp:443 tcp:8443 >/dev/null
python3 run_android.py emulator-5560 18481 c2 3 3000 0 base_map,ga_default,amplitude_default,firebase,hyperkit_core,hyperkit_ctx,adjust,facebook > results/android_c2.log 2>&1
pkill -f fbsrv.py
log "Unity clean series"
mv results/unity results/unity_loaded 2>/dev/null; ./run_unity_series.sh > results/unity_series_clean.log 2>&1
log "server clean series"
mv results/server results/server_loaded 2>/dev/null; mkdir -p results/server; ./run_server_series.sh > results/server_series_clean.log 2>&1
log "host clean runs"
mkdir -p results/host_clean; export DALIYS_ZSTD=$PWD/../Runtime/Plugins/macOS/libdaliys_zstd.dylib
for i in 1 2 3 4 5; do dotnet bench/bin/Release/net10.0/V7Bench.dll work clean_all_$i all 100000000 results/host_clean/all_$i.json; done
for i in 1 2; do PHASES=1 dotnet bench/bin/Release/net10.0/V7Bench.dll work clean_phases_$i holdout 100000000 results/host_clean/phases_$i.json; done
dotnet bench/bin/Release/net10.0/V7Bench.dll profile work holdout > results/host_clean/profile.json
dotnet bench/bin/Release/net10.0/V7Bench.dll memory work > results/host_clean/memory.json
log "ALL DONE"; echo done > results/driver_done.txt
