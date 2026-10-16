#!/bin/sh
# Reproduce every number in transport-v2/. Needs Python 3.11+ and network only for measure_tls.sh.
#   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && PY=.venv/bin/python sh run_all.sh
set -e
PY=${PY:-python3}
mkdir -p results
$PY gen.py > results/dataset_base.txt
$PY gen.py rich > results/dataset_rich.txt
$PY test_roundtrip.py > results/roundtrip.txt
$PY make_example.py > /dev/null
$PY entropy_floor.py > results/entropy_floor.txt
$PY run_http.py > results/http.md
$PY run_cpu.py > results/cpu.md
$PY run_conservative.py > results/conservative.md
$PY run_stateful.py base > results/stateful_base.md
$PY run_stateful.py rich > results/stateful_rich.md
$PY run_size.py 10 base > results/sizes_base.md &
$PY run_size.py 10 rich > results/sizes_rich.md &
wait
sh measure_tls.sh > results/tls.txt || echo "TLS measurement needs network; skipped"
echo done
