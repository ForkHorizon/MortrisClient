#!/bin/bash
# #0127 again, controlled: the project first learns 1000+ shapes and a trained dictionary (3 warm-up runs of the midcore train stream), then the same midcore slice is sent
# (T4) with the default server limits and (T5) with the limits lifted. If #0127 is the limiter or the catalog / dictionary, T4 and T5 differ; if both are fine it was an artefact.
# Usage: sep_0127b.sh SERIAL PORT   (emulator)
cd "$(dirname "$0")/.."
S=$1; P=$2
unset MORTRIS_INGEST_INSTALL_PER_MIN MORTRIS_INGEST_INSTALL_BURST MORTRIS_INGEST_PROJECT_RPS MORTRIS_INGEST_PROJECT_BURST MORTRIS_INGEST_INSTALL_EVENTS_PER_MIN MORTRIS_INGEST_INSTALL_EVENTS_BURST
tools/stack_start.sh sepb 54416 18116 seed-v7
cell() { python3 tools/run_cell.py --serial $S --port $P --label $1 --sdk mortris_v8 --out results/sep0127b --data $2 --stack sepb --project midcore_test --no-install --dump --tail-max 300 --quiet 150 --expect $3 --kv scenario=perframe perframe=20 n=$3 marker=1; }
for i in 1 2 3; do cell warm_$i midcore_train_20k.jsonl 3000; done
cell T4_default_limits midcore_slice_00.jsonl 2000
. work/stacks/sepb.env
lsof -ti tcp:18116 -sTCP:LISTEN | xargs kill; sleep 2
export MORTRIS_INGEST_INSTALL_PER_MIN=6000 MORTRIS_INGEST_INSTALL_BURST=3000 MORTRIS_INGEST_PROJECT_RPS=3000 MORTRIS_INGEST_PROJECT_BURST=5000 MORTRIS_INGEST_INSTALL_EVENTS_PER_MIN=600000 MORTRIS_INGEST_INSTALL_EVENTS_BURST=3000000
DSN="postgres://postgres@127.0.0.1:$PGPORT/mortris_cmp?sslmode=disable"
export MORTRIS_MIGRATOR_DSN=$DSN MORTRIS_WRITER_DSN=$DSN MORTRIS_READER_DSN=$DSN LISTEN_ADDR=0.0.0.0:18116 MORTRIS_TRANSPORT_MASTER_KEYS=k:0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f20
(cd /Users/daliys/Daliys/Web/MortrisServer-v8 && "$OLDPWD/work/analytics-server-v8" serve >"$TMP/server2.log" 2>&1 &)
sleep 4
cell T5_lifted_limits midcore_slice_01.jsonl 2000
echo SEP_B_DONE
