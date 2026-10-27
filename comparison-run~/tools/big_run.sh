#!/bin/bash
# The big run on VIRTUAL devices only (the phone is not touched). Two emulators work in parallel:
#   A (emulator-5554, port 18190): stage-profile matrix with the profiling APK (init, rate, batch, burst), then the Development APK for allocation attribution
#   B (emulator-5556, port 18191): #0127 separation, network matrix (drain over 2G..5G, Wi-Fi flapping), stage-profile (profile presets, TLS, backlog), 30-minute offline
# CPU numbers of an emulator are not phone numbers: read proportions between stages, bytes, requests and times, not absolute microseconds.
cd "$(dirname "$0")/.."
A=~/Library/Android/sdk/platform-tools/adb
boot() { # name port
  ~/Library/Android/sdk/emulator/emulator -avd $1 -port $2 -no-window -no-audio -no-snapshot -no-boot-anim >work/emu_$2.log 2>&1 &
  $A wait-for-device; until [ "$($A -s emulator-$2 shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ]; do sleep 3; done; sleep 10
}
warm() { # serial port stack apk
  $A -s $1 install -r $4 >/dev/null
  for i in 1 2; do python3 tools/run_cell.py --serial $1 --port $2 --label warm_$i --sdk mortris_v8 --out results/bigwarm_$3 --data puzzle_train_20k.jsonl --stack $3 --no-install --expect 3000 --tail-max 100 --quiet 20 --kv scenario=perframe perframe=20 n=3000 flush_at_end=1 | tail -1; done
}
case "$1" in
A)
  boot Mortris_API_35 5554
  tools/stack_start.sh bigA 54421 18121 seed-v7
  warm emulator-5554 18190 bigA work/cmp-prof-arm64.apk
  PORT=18190 python3 tools/matrix_profile.py emulator-5554 bigprof_A bigA init,rate,batch,burst 2
  PORT=18190 python3 tools/matrix_profile.py emulator-5554 bigprof_A bigA dev 2
  echo CHAIN_A_DONE ;;
B)
  boot Pixel_8 5556
  tools/stack_start.sh bigB 54422 18122 seed-v7
  warm emulator-5556 18191 bigB work/cmp-new-arm64.apk
  tools/sep_0127b.sh emulator-5556 18191
  python3 tools/matrix_net.py emulator-5556 18191 bigB bignet drain,flap
  PORT=18191 python3 tools/matrix_profile.py emulator-5556 bigprof_B bigB profile,tls,backlog 1
  $A -s emulator-5556 install -r work/cmp-new-arm64.apk >/dev/null
  python3 tools/matrix_net.py emulator-5556 18191 bigB bignet long
  echo CHAIN_B_DONE ;;
esac
