#!/bin/sh
set -eu
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
PY=${PY:-../../transport-v3/06-experiments/.venv/bin/python}
"$PY" -m unittest discover -s . -p 'test*7.py' > results/cross-tests.log 2>&1
"$PY" bench_cross7.py > results/cross-benchmark.log 2>&1
"$PY" export_cross7.py
"$PY" verify7.py
"$PY" snapshot.py
"$PY" freeze7.py
