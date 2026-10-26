#!/bin/sh
set -eu
export PYTHONDONTWRITEBYTECODE=1
PY=${PY:-.venv/bin/python}
# Make interpreter absolute before entering the baseline copy.
PY=$($PY -c 'import sys;print(sys.executable)')
mkdir -p results
$PY external_audit.py > results/external-audit.log 2>&1
(cd v2-rerun && PY="$PY" sh run_all.sh) > results/v2-full-rerun.log 2>&1
$PY compare_v2.py > results/v2-fresh-comparison.json
$PY ../../transport-v3/06-experiments/test_v3.py > results/v3-tests-rerun.json
$PY corpus_manifest.py
$PY bench_v4.py > results/paired-matrix.log 2>&1
$PY evaluate_final.py > results/holdout-resources.log 2>&1
$PY extreme_v4.py > results/extreme-v4.log 2>&1
$PY queue_storage.py > results/queue-storage.log 2>&1
$PY native_memory.py > results/native-memory.log 2>&1
$PY native_build.py > results/native-build.log 2>&1
$PY network_v4.py
$PY header_experiment.py
$PY memory_floor.py > results/memory-floor.log 2>&1
$PY final_passes_v4.py > results/final-passes-v4.log 2>&1
$PY test_v4.py > results/tests.log 2>&1
$PY export_reports.py
$PY verify.py > results/verification.json
