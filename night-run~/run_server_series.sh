#!/bin/bash
cd "$(dirname "$0")"; export PGPORT=54341 HTTP_PORT=18092
for rep in 1 2 3; do for mode in v1 v7; do
  [ -f results/server/${mode}_seq_r$rep/result.json ] || { ./run_server_load.sh $mode ${mode}_seq_r$rep 24 60000 1 > results/server_last.log 2>&1 || echo "FAILED seq $mode $rep"; echo "$(date +%T) seq $mode r$rep"; }
  [ -f results/server/${mode}_par6_r$rep/result.json ] || { ./run_server_load.sh $mode ${mode}_par6_r$rep 24 60000 6 > results/server_last.log 2>&1 || echo "FAILED par $mode $rep"; echo "$(date +%T) par6 $mode r$rep"; }
done; done
echo done > results/server/series_done.txt
