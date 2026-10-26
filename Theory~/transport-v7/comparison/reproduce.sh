#!/bin/sh
# Reproduces comparison results WITHOUT touching frozen 06-experiments/results.
# Needs the private day dump (results/private/puzzle-2026-10-16.jsonl.gz) and the V3 venv.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd); T=${TMPDIR:-/tmp}/v7-repro; PY=${PY:-$HERE/../../transport-v3/06-experiments/.venv/bin/python}
export PYTHONDONTWRITEBYTECODE=1
rm -rf "$T"; mkdir -p "$T/Theory~/transport-v7" "$T/Theory~/transport-v6"
for d in "$HERE"/../../transport-*; do b=$(basename "$d"); [ "$b" = transport-v7 ] || [ "$b" = transport-v6 ] || ln -s "$d" "$T/Theory~/$b"; done
rsync -a --exclude results/private --exclude 'native/bin' --exclude 'native/obj*' "$HERE/../06-experiments" "$T/Theory~/transport-v7/"
rsync -a "$HERE/../../transport-v6/06-experiments" "$T/Theory~/transport-v6/"
rsync -a --exclude 'android*' --exclude frames --exclude 'emulator*' --exclude '*.so' "$HERE/../06-experiments/results/private/" "$T/Theory~/transport-v7/06-experiments/results/private/"
cd "$T/Theory~/transport-v7/06-experiments"
dotnet build native/Frames.csproj -c Release --nologo >/dev/null; dotnet build native/Columns.csproj -c Release --nologo >/dev/null
"$PY" native_frames7.py > "$HERE/results/repro-native-frames.log"   # C1, C2, C6(host)
"$PY" bench_real7.py   > "$HERE/results/repro-bench-real.log"      # C3 + ablations
"$PY" "$HERE/scripts/synth_bench.py"                                 # C4/C5 (writes results/synth-bench.json)
"$PY" "$HERE/scripts/identity_harness.py" >/dev/null                 # C9
