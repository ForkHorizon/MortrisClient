#!/bin/sh
# Run from 06-experiments. Original V2 is read-only; reproduction writes only here.
set -eu
export PYTHONDONTWRITEBYTECODE=1
PY=${PY:-.venv/bin/python}
mkdir -p results
$PY audit.py > results/audit.json
(cd v2-reproduction && PY=../.venv/bin/python sh run_all.sh) > results/v2-run-all.log 2>&1
$PY reproduction_check.py > results/reproduction-check.json
$PY corpus_manifest.py > results/corpus-manifest.json
$PY bench.py > results/bench.log 2>&1
$PY refine.py > results/refine.log 2>&1
$PY further.py > results/further.log 2>&1
$PY extreme.py > results/extreme.log 2>&1
$PY final_passes.py > results/final-passes.log 2>&1
$PY unicode_keys.py > results/unicode-keys.json
$PY checkpoint.py > results/checkpoint.json
$PY test_v3.py > results/v3-tests.json
$PY network.py > results/network.json
$PY cpu_v3.py > results/cpu-v3.json
$PY extras.py > results/extras.json
$PY native_size.py > results/native-size.json
$PY export_reports.py
$PY verify.py > results/verification.json
