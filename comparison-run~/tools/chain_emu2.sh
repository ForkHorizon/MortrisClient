#!/bin/bash
cd "$(dirname "$0")/.."
S=emulator-5556; P=18191
~/Library/Android/sdk/platform-tools/adb -s $S install -r work/cmp2-arm64.apk >/dev/null
for i in 1 2; do python3 tools/run_cell.py --serial $S --port $P --label warm_v8_$i --sdk mortris_v8 --out results/warm2 --data puzzle_train_20k.jsonl --stack emu2 --no-install --expect 3000 --tail-max 100 --quiet 20 --kv scenario=perframe perframe=20 n=3000 flush_at_end=1 | tail -1; done
python3 tools/matrix_chaos.py $S $P emu2 chaos 0 kill,net_loss,net_bad,offline
python3 tools/matrix_param.py $S $P emu2 param batch,rate,burst
