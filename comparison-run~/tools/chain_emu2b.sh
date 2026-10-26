#!/bin/bash
cd "$(dirname "$0")/.."
S=emulator-5556; P=18191
python3 tools/matrix_chaos.py $S $P emu2 chaos 0 net_loss,net_bad,offline
python3 tools/matrix_param.py $S $P emu2 param batch,rate,burst
