#!/bin/sh
set -eu
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
PY=${PY:-../../transport-v3/06-experiments/.venv/bin/python}
dotnet build native/Frames.csproj -c Release --nologo > results/frame-build.log 2>&1
dotnet build native/UnityColumns.csproj -c Release --nologo > results/csharp-netstandard.log 2>&1
"$PY" -m unittest discover -s . -p 'test*7.py' > results/frame-python-tests.log 2>&1
"$PY" native_frames7.py > results/native-frames.log 2>&1
"$PY" export_frames7.py
"$PY" export_reports7.py
"$PY" verify7.py
"$PY" snapshot.py
"$PY" freeze7.py
