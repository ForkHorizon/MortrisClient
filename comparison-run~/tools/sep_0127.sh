#!/bin/bash
# Separates #0127: (T1) midcore on a fresh project, default limits; (T2) the same project now holding a large shape catalog, default limits; (T3) same catalog, limits lifted.
cd "$(dirname "$0")/.."
A=~/Library/Android/sdk/platform-tools/adb; S=emulator-5554; P=18190
~/Library/Android/sdk/emulator/emulator -avd Mortris_API_35 -port 5554 -no-window -no-audio -no-snapshot -no-boot-anim >work/emu_sep.log 2>&1 &
$A wait-for-device; until [ "$($A -s $S shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ]; do sleep 3; done; sleep 10
$A -s $S install -r work/cmp5-arm64.apk >/dev/null
unset MORTRIS_INGEST_INSTALL_PER_MIN MORTRIS_INGEST_INSTALL_BURST MORTRIS_INGEST_PROJECT_RPS MORTRIS_INGEST_PROJECT_BURST
tools/stack_start.sh sep 54415 18115 seed-v7
cell() { python3 tools/run_cell.py --serial $S --port $P --label $1 --sdk mortris_v8 --out results/sep0127 --data midcore_slice_00.jsonl --stack sep --project midcore_test --no-install --dump --tail-max 300 --quiet 150 --expect 2000 --kv scenario=perframe perframe=20 n=2000 marker=1 flush_at_end=1; }
cell T1_fresh_default
cell T1b_second_default_big_catalog     # this install downloads the catalog the first run created
. work/stacks/sep.env
# restart the server on the same database with the limits lifted
lsof -ti tcp:18115 -sTCP:LISTEN | xargs kill; sleep 2
export MORTRIS_INGEST_INSTALL_PER_MIN=6000 MORTRIS_INGEST_INSTALL_BURST=3000 MORTRIS_INGEST_PROJECT_RPS=3000 MORTRIS_INGEST_PROJECT_BURST=5000
DSN="postgres://postgres@127.0.0.1:$PGPORT/mortris_cmp?sslmode=disable"
export MORTRIS_MIGRATOR_DSN=$DSN MORTRIS_WRITER_DSN=$DSN MORTRIS_READER_DSN=$DSN LISTEN_ADDR=0.0.0.0:18115 MORTRIS_TRANSPORT_MASTER_KEYS=k:0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f20
(cd /Users/daliys/Daliys/Web/MortrisServer-v8 && "$PWD/../../UnityProjects/MortrisUnity/Assets/MortrisClient/comparison-run~/work/analytics-server-v8" serve >"$TMP/server2.log" 2>&1 &)
sleep 4
cell T3_big_catalog_lifted
echo SEP_DONE
