#!/bin/bash
cd "$(dirname "$0")/.."
for n in 50 100 190; do for m in v1 v7 v8; do [ -f results/server/${m}_$n/result.json ] || tools/server_load.sh $m ${m}_$n $n > /dev/null 2>&1; echo "$(date +%H:%M:%S) ${m}_$n done"; done; done
echo SERVER_DONE
