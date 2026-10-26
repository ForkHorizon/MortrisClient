#!/bin/sh
set -eu
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
PY=${PY:-../../transport-v3/06-experiments/.venv/bin/python}
(cd go && go test ./...) > results/go-frame-tests.log 2>&1
(cd go && go test -fuzz FuzzFullFrameBoundary -fuzztime 10s -parallel 2) > results/go-frame-fuzz.log 2>&1
"$PY" go_frames7.py > results/go-frames.log 2>&1
"$PY" export_go_frames7.py
"$PY" export_reports7.py
"$PY" verify7.py
"$PY" snapshot.py
"$PY" freeze7.py
