#!/bin/bash
cd "$(dirname "$0")/.."
S=emulator-5556; P=18191
while ! grep -q CHAOS_DONE work/chaos_off5.out; do sleep 20; done
python3 tools/matrix_chaos.py $S $P emu2 chaos 0 net_loss mortris_v1
# Amplitude 2.40.1 drain: wait for the whole queue (no quiet-stop before 7 min of silence)
python3 tools/run_cell.py --serial $S --port $P --label drain_amplitude --sdk amplitude --out results/drain --data puzzle_slice_13.jsonl --stack emu2 --no-install --dump --tail-max 2400 --quiet 420 --kv scenario=perframe perframe=20 n=2000 marker=1
python3 tools/fidelity.py results/drain/drain_amplitude amplitude data/puzzle_slice_13.jsonl 2000 > results/drain/drain_amplitude/fidelity.json
BURST_TAIL=900 BURST_KS=6000 BURST100=none python3 tools/matrix_param.py $S $P emu2 param2 burst
echo CHAIN2C_DONE
