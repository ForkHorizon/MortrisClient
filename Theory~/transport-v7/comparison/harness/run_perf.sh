#!/bin/sh
# CPU/alloc profile of Android SDKs on the de-identified Puzzle replay (EMULATORS, 5 in parallel, DNS blocked). Needs replay-private/puzzle_clean.jsonl.
set -u; cd "$(dirname "$0")"; ADB=~/Library/Android/sdk/platform-tools/adb; PY=${PY:?set PY to the venv python}
pkill -f qemu-system; sleep 2
for p in 5554 5556 5558 5560 5562; do (nohup ~/Library/Android/sdk/emulator/emulator -avd Mortris_API_35 -read-only -port $p -no-window -no-audio -no-boot-anim -no-snapshot-save -gpu swiftshader_indirect -dns-server 127.0.0.1 >/dev/null 2>&1 &); sleep 3; done
for s in emulator-5554 emulator-5556 emulator-5558 emulator-5560 emulator-5562; do $ADB -s $s wait-for-device; for i in $(seq 1 70); do [ "$($ADB -s $s shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ] && break; sleep 3; done; $ADB -s $s install -r android/app/build/outputs/apk/release/app-release.apk >/dev/null; done
i=0; for s in emulator-5554 emulator-5556 emulator-5558 emulator-5560 emulator-5562; do OUTDIR=sdk-runs-perf CORPORA=puzzle_clean REPLAY_DIR=$PWD/replay-private MODES=base_parse,base_map,amplitude_default,ga_default $PY run_matrix.py 5 $i 5 $s $((18431+i)) > ../results/sdk-matrix-perf-$i.log 2>&1 & i=$((i+1)); done; wait
rm -f ../results/sdk-runs-perf/*.sample-*
for s in emulator-5554 emulator-5556 emulator-5558 emulator-5560 emulator-5562; do $ADB -s $s emu kill >/dev/null 2>&1; done
