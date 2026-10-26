#!/bin/sh
set -eu
export PYTHONDONTWRITEBYTECODE=1
cd "$(dirname "$0")"
PY=${PY:-python3}
"$PY" test_v6.py > results/tests.log 2>&1
"$PY" bench.py > results/bench.log 2>&1
"$PY" schema_tools.py
"$PY" native_check.py > results/native.log 2>&1
"$PY" confirm.py > results/confirmation.log 2>&1
"$PY" fixtures.py
"$PY" field_costs.py
"$PY" export_reports.py
"$PY" verify.py
