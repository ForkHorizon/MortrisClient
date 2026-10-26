#!/bin/sh
set -eu
export PYTHONDONTWRITEBYTECODE=1
PY=${PY:-.venv/bin/python}
PY=$($PY -c 'import sys;print(sys.executable)')
mkdir -p results
(cd submission-rerun && "$PY" baseline_v4.py > baseline-rerun.log 2>&1)
for profile in base rich alt drift; do
 (cd submission-rerun && "$PY" run_matrix.py "$profile" > "$profile-rerun.log" 2>&1)
done
(cd submission-rerun && "$PY" test_roundtrip.py > roundtrip-rerun.log 2>&1)
(cd submission-rerun && "$PY" test_mutation.py > mutation-rerun.log 2>&1)
(cd submission-rerun && "$PY" session_reset.py > session-reset-rerun.log 2>&1)
(cd submission-rerun && "$PY" wire_eval.py > wire-rerun.log 2>&1)
(cd submission-rerun && PYTHONHASHSEED=0 "$PY" fixed_table.py base rich alt > fixed-rerun.log 2>&1)
"$PY" compare_submission.py
"$PY" hashseed_audit.py
for profile in base rich alt drift; do
 "$PY" probe_v5.py "$profile" > "results/probe-$profile.log" 2>&1
 "$PY" bench_v5.py "$profile" > "results/bench-$profile.log" 2>&1
done
"$PY" memory_v5.py > results/memory.log 2>&1
"$PY" compact_prior.py > results/compact-prior.log 2>&1
"$PY" mismatch_v5.py > results/mismatch.log 2>&1
"$PY" miss_cost.py > results/miss-cost.log 2>&1
"$PY" network_v5.py > results/network.log 2>&1
"$PY" native_check.py > results/native-conformance.log 2>&1
"$PY" asset_manifest.py
"$PY" corpus_manifest.py
"$PY" fixtures.py
"$PY" test_v5.py > results/tests.log 2>&1
"$PY" test_recovery.py > results/recovery-tests.log 2>&1
"$PY" extra_tests.py > results/extra-tests.log 2>&1
"$PY" mutation_v5.py > results/mutations.log 2>&1
"$PY" baseline-v4-tests/test_v4.py > results/v4-tests-rerun.log 2>&1
"$PY" export_reports.py
"$PY" verify.py > results/verification.json
