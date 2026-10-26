#!/bin/bash
cd "$(dirname "$0")"; export DALIYS_ZSTD=$PWD/../Runtime/Plugins/macOS/libdaliys_zstd.dylib; W=$PWD/work
mk() { d=$W/lc_c$1_b$2; mkdir -p $d; ln -sf $W/lc_catalog_$1.json $d/catalog.json; ln -sf $W/lc_dict_$1.bin $d/dictionary.bin; ln -sf $W/lc_holdout_b$2.jsonl $d/batches.jsonl; echo $d; }
for rep in 1 2; do
  for pct in 2 5 10 25 50; do d=$(mk $pct 100); dotnet bench/bin/Release/net10.0/V7Bench.dll $d lc_c${pct}_b100_r$rep holdout 100000000 results/lc/c${pct}_b100_r$rep.json; done
  for b in 10 30; do d=$(mk 25 $b); dotnet bench/bin/Release/net10.0/V7Bench.dll $d lc_c25_b${b}_r$rep holdout 100000000 results/lc/c25_b${b}_r$rep.json; done
  d=$(mk 25 100); PHASES=1 dotnet bench/bin/Release/net10.0/V7Bench.dll $d phases_c25_b100_r$rep holdout 100000000 results/lc/phases_c25_b100_r$rep.json
done
echo done > results/lc/done.txt
