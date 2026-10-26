#!/bin/bash
cd "$(dirname "$0")"
for n in 1500 3000 6000 12000; do python3 run_android.py emulator-5554 1849$((n/1500)) burst_ga_$n 1 $n 240 ga_default; done
python3 run_android.py emulator-5554 18499 burst_hk_12000 1 12000 60 hyperkit_ctx
python3 run_android.py emulator-5554 18498 burst_amp_1500 1 1500 600 amplitude_b100
echo done > results/burst_done.txt
