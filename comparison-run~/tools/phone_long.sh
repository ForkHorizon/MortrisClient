#!/bin/bash
# Phone: 20-minute play session (5 events/s, 6000 events, natural SDK timers, no flush at the end) per SDK. Waits for the phone burst series.
cd "$(dirname "$0")/.."
S=0006814AG001387
for sdk in mortris_v8 none mortris_v1 ga; do
  [ -f results/phone_long/${sdk}_10min/run.json ] || python3 tools/run_cell.py --serial $S --label ${sdk}_10min --sdk $sdk --out results/phone_long --data puzzle_hold_100k.jsonl --stack cpu --no-install --scen-max 1500 --tail-max 400 --quiet 200 --kv scenario=rate hz=5 n=3000 marker=0
done
echo PHONE_LONG_DONE
