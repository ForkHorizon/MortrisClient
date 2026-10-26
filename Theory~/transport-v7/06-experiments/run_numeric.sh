#!/bin/sh
set -eu
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
PY=${PY:-../../transport-v3/06-experiments/.venv/bin/python}
"$PY" test_v7.py > results/tests.log 2>&1
"$PY" test_numeric7.py > results/numeric-tests.log 2>&1
dotnet build native/Columns.csproj -c Release --nologo > results/csharp-build.log 2>&1
dotnet build native/UnityColumns.csproj -c Release --nologo > results/csharp-netstandard.log 2>&1
"$PY" probe_columns7.py > results/integer-probe.log 2>&1
"$PY" bench_numeric7.py > results/numeric-benchmark.log 2>&1
"$PY" native_numeric7.py > results/native-numeric.log 2>&1
"$PY" go_check7.py --numeric > results/go-check-numeric.log 2>&1
"$PY" export_reports7.py
"$PY" verify7.py
"$PY" snapshot.py
"$PY" freeze7.py
