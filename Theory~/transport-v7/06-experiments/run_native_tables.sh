#!/bin/sh
set -eu
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
PY=${PY:-../../transport-v3/06-experiments/.venv/bin/python}
"$PY" -m unittest discover -s . -p 'test*7.py' > results/tables-tests.log 2>&1
dotnet build native/Columns.csproj -c Release --nologo > results/csharp-build.log 2>&1
dotnet build native/UnityColumns.csproj -c Release --nologo > results/csharp-netstandard.log 2>&1
"$PY" native_tables7.py > results/native-tables.log 2>&1
(cd go && go test ./...) > results/go-table-tests.log 2>&1
"$PY" go_check7.py --tables > results/go-check-tables.log 2>&1
"$PY" go_check7.py --numeric > results/go-check-numeric.log 2>&1
"$PY" go_check7.py > results/go-check.log 2>&1
"$PY" export_reports7.py
# run_unity7.sh consumes these fixtures and performs aggregate verification/freezing.
