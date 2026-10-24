#!/bin/bash
# Full scenario matrix. Usage: RUNSET=emu ./run_matrix.sh [SERIAL]
PR=$(cd "$(dirname "$0")" && pwd); S=${1:-}
run() { "$PR/run_prof.sh" "$@" ${S:+} >/dev/null 2>&1 || echo "FAILED $1"; echo "done $1 $(date +%H:%M:%S)"; }
for m in v7 v1; do
  run ${m}_single   $m single   "n=15 gap=6" $S
  run ${m}_burst100 $m burst    "n=5 k=100 gap=12" $S
  run ${m}_persec   $m persec   "n=90" $S
  run ${m}_perframe1 $m perframe "n=1200 perframe=1" $S
  run ${m}_burst20f $m perframe "n=2800 perframe=20" $S
done
run none_perframe1 none perframe "n=1200 perframe=1" $S
run none_burst20f  none perframe "n=2800 perframe=20" $S
echo MATRIX_DONE
