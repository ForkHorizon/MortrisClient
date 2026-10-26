#!/bin/bash
cd "$(dirname "$0")/.."
for n in 100 190; do for m in v1 v7 v8; do [ -f results/server/${m}_${n}_p32/result.json ] || LOADGEN_PAR=32 tools/server_load.sh $m ${m}_${n}_p32 $n > /dev/null 2>&1; echo "$(date +%H:%M:%S) ${m}_${n}_p32 done"; done; done
echo SERVER2_DONE
