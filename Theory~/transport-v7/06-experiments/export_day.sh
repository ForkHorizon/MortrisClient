#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
mkdir -p results/private
ssh -o BatchMode=yes -o ConnectTimeout=10 daliys@143.14.22.61 'set -o pipefail; sudo -n -u postgres psql -Xq -d mortris -v ON_ERROR_STOP=1 | gzip -1' < export_day.sql > results/private/puzzle-2026-10-16.jsonl.gz.tmp
mv results/private/puzzle-2026-10-16.jsonl.gz.tmp results/private/puzzle-2026-10-16.jsonl.gz
