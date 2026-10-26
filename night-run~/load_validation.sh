#!/bin/bash
# 3 reps at each artificial load level (busy processes on 10 cores). Output results/host/load_<N>_<rep>.json
cd "$(dirname "$0")/bench"; export DALIYS_ZSTD=$PWD/../../Runtime/Plugins/macOS/libdaliys_zstd.dylib
for N in 0 6 12 20; do for rep in 1 2 3; do
  echo "$(date +%T) level $N rep $rep"
  SP=""
  if [ $N -gt 0 ]; then ../stress.sh $N 50 & SP=$!; fi
  sleep 2
  dotnet bin/Release/net10.0/V7Bench.dll ../work load${N}_$rep all 100000000 ../results/host/load_${N}_${rep}.json
  [ -n "$SP" ] && wait $SP
done; done
echo finished > ../results/host/load_done.txt
