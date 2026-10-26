#!/bin/bash
cd "$(dirname "$0")/.."
while ! grep -q PARAM_DONE work/param1c.out; do sleep 20; done
OFFLINE_N=1800 OFFLINE_HZ=10 OFFLINE_QUIET=600 python3 tools/matrix_chaos.py emulator-5554 18190 emu chaos_b 0 offline mortris_v8,mortris_v1
echo CHAIN1B_DONE
