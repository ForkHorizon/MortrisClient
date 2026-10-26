#!/bin/sh
set -eu
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
PY=${PY:-../../transport-v3/06-experiments/.venv/bin/python}
mkdir -p results
"$PY" snapshot.py
"$PY" test_v7.py > results/tests.log 2>&1
"$PY" test_numeric7.py > results/numeric-tests.log 2>&1
dotnet build native/Columns.csproj -c Release --nologo > results/csharp-build.log 2>&1
dotnet build native/UnityColumns.csproj -c Release --nologo > results/csharp-netstandard.log 2>&1
"$PY" bench7.py > results/bench.log 2>&1
"$PY" native_check7.py > results/native-csharp.log 2>&1
"$PY" bench_real7.py > results/bench-real.log 2>&1
"$PY" derive_baselines.py > results/matched-baselines.log 2>&1
"$PY" go_check7.py > results/go-check.log 2>&1
"$PY" source_audit.py
"$PY" emulator_queue7.py > results/emulator-queue.log 2>&1
"$PY" export_reports7.py
"$PY" verify7.py
"$PY" snapshot.py
"$PY" freeze7.py
