# Profiling tables (emu_final)

Per event = stage total / events in scenario. Times in µs. cpu = thread CPU, wall = elapsed incl. blocking. Stages nest (inclusive).


## idle_none

events=1, scenario_ms=60025, process CPU: scenario 13120000 µs/event, drain 0 µs/event, total 13120000 µs/event; GC0/1/2=0/0/0; Track µs p50/p95/p99=0.1/0.1/0.1; frame ms p99=0.00; Unity main-thread GC alloc/event=604464 B (6345.00 allocs); ART(Java) alloc/event=131072 B, ART GCs=1; PSS start/peak MB=160/162; db_events=0, packets_v2=0, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|

Traffic: V7 packets 0 (0 B), V1 batches 0 (gzip 0 B, json 0 B) -> 0.0 B/event body; persist_calls=None for 1 events (avg 0.00 events per call)

## idle_v1

events=1, scenario_ms=60021, process CPU: scenario 13460000 µs/event, drain 10000 µs/event, total 13470000 µs/event; GC0/1/2=5/5/5; Track µs p50/p95/p99=30.8/30.8/30.8; frame ms p99=0.03; Unity main-thread GC alloc/event=1321089 B (12724.00 allocs); ART(Java) alloc/event=393216 B, ART GCs=1; PSS start/peak MB=160/165; db_events=3, packets_v2=0, batches_v1=3

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 29.0 | 29.0 | 0 |
| track_enqueue | 1.00 | 4.0 | 3.0 | 0 |
| persist_total | 16.00 | 7950.0 | 18148.0 | 0 |
| snapshot_batch | 10.00 | 18.0 | 20.0 | 0 |
| jni_enqueue_batch | 1.00 | 864.0 | 1256.0 | 0 |
| uploader_flush | 10.00 | 5831.0 | 15308.0 | 0 |
| jni_get_state | 8.00 | 533.0 | 548.0 | 0 |
| jni_read_batch | 9.00 | 4665.0 | 9892.0 | 0 |
| jni_delete_ack | 1.00 | 166.0 | 166.0 | 0 |
| v1_parse_queued | 1.00 | 34.0 | 34.0 | 0 |
| v1_send_batch(json+gzip+http) | 1.00 | 323.0 | 4301.0 | 0 |
| v1_gzip_body | 1.00 | 123.0 | 290.0 | 0 |
| http_send(wall) | 1.00 | 147.0 | 3956.0 | 0 |

Traffic: V7 packets 0 (0 B), V1 batches 1 (gzip 629 B, json 1079 B) -> 629.0 B/event body; persist_calls=16 for 1 events (avg 0.06 events per call)

## idle_v7

events=1, scenario_ms=60031, process CPU: scenario 13500000 µs/event, drain 10000 µs/event, total 13510000 µs/event; GC0/1/2=5/5/5; Track µs p50/p95/p99=72.6/72.6/72.6; frame ms p99=0.07; Unity main-thread GC alloc/event=1436014 B (14179.00 allocs); ART(Java) alloc/event=425984 B, ART GCs=1; PSS start/peak MB=160/169; db_events=3, packets_v2=3, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 52.0 | 71.0 | 0 |
| track_enqueue | 1.00 | 25.0 | 42.0 | 0 |
| persist_total | 16.00 | 12940.0 | 22916.0 | 0 |
| snapshot_batch | 10.00 | 19.0 | 22.0 | 0 |
| jni_enqueue_batch | 1.00 | 913.0 | 1217.0 | 0 |
| uploader_flush | 10.00 | 10890.0 | 20459.0 | 0 |
| jni_get_state | 8.00 | 594.0 | 639.0 | 0 |
| jni_read_batch | 9.00 | 7399.0 | 10188.0 | 0 |
| jni_delete_ack | 1.00 | 202.0 | 202.0 | 0 |
| v7_encode(parse+pack+zstd) | 1.00 | 76.0 | 76.0 | 0 |
| v7_post_packet | 1.00 | 352.0 | 7080.0 | 0 |

Traffic: V7 packets 1 (135 B), V1 batches 0 (gzip 0 B, json 0 B) -> 135.0 B/event body; persist_calls=16 for 1 events (avg 0.06 events per call)

## none_burst20f

events=2800, scenario_ms=4664, process CPU: scenario 357 µs/event, drain 0 µs/event, total 357 µs/event; GC0/1/2=0/0/0; Track µs p50/p95/p99=0.0/0.1/0.2; frame ms p99=0.02; Unity main-thread GC alloc/event=283 B (3.32 allocs); ART(Java) alloc/event=23 B, ART GCs=0; PSS start/peak MB=173/174; db_events=0, packets_v2=0, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|

Traffic: V7 packets 0 (0 B), V1 batches 0 (gzip 0 B, json 0 B) -> 0.0 B/event body; persist_calls=None for 2800 events (avg 0.00 events per call)

## none_perframe1

events=1200, scenario_ms=40098, process CPU: scenario 7517 µs/event, drain 0 µs/event, total 7517 µs/event; GC0/1/2=0/0/0; Track µs p50/p95/p99=0.1/0.2/0.3; frame ms p99=0.01; Unity main-thread GC alloc/event=639 B (7.30 allocs); ART(Java) alloc/event=82 B, ART GCs=1; PSS start/peak MB=165/168; db_events=0, packets_v2=0, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|

Traffic: V7 packets 0 (0 B), V1 batches 0 (gzip 0 B, json 0 B) -> 0.0 B/event body; persist_calls=None for 1200 events (avg 0.00 events per call)

## v1_burst100

events=500, scenario_ms=60159, process CPU: scenario 28440 µs/event, drain 20 µs/event, total 28460 µs/event; GC0/1/2=18/18/18; Track µs p50/p95/p99=17.9/38.0/145.0; frame ms p99=4.14; Unity main-thread GC alloc/event=19832 B (95.72 allocs); ART(Java) alloc/event=6832 B, ART GCs=1; PSS start/peak MB=162/175; db_events=502, packets_v2=0, batches_v1=7

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 21.3 | 30.6 | 0 |
| track_enqueue | 1.00 | 1.6 | 5.4 | 0 |
| persist_total | 0.04 | 187.6 | 718.9 | 0 |
| snapshot_batch | 0.03 | 0.3 | 0.3 | 0 |
| jni_enqueue_batch | 0.01 | 78.0 | 115.4 | 0 |
| uploader_flush | 0.03 | 104.7 | 598.2 | 0 |
| jni_get_state | 0.02 | 2.9 | 3.1 | 0 |
| jni_read_batch | 0.03 | 32.6 | 43.2 | 0 |
| jni_delete_ack | 0.01 | 15.7 | 19.8 | 0 |
| v1_parse_queued | 0.01 | 28.1 | 35.1 | 0 |
| v1_send_batch(json+gzip+http) | 0.01 | 19.4 | 490.8 | 0 |
| v1_gzip_body | 0.01 | 11.3 | 12.7 | 0 |
| http_send(wall) | 0.01 | 2.6 | 460.0 | 0 |

Traffic: V7 packets 0 (0 B), V1 batches 5 (gzip 43229 B, json 563349 B) -> 86.5 B/event body; persist_calls=21 for 500 events (avg 23.81 events per call)

## v1_burst20f

events=2800, scenario_ms=4663, process CPU: scenario 493 µs/event, drain 3554 µs/event, total 4046 µs/event; GC0/1/2=20/20/20; Track µs p50/p95/p99=14.9/34.9/72.5; frame ms p99=4.75; Unity main-thread GC alloc/event=28464 B (118.35 allocs); ART(Java) alloc/event=9301 B, ART GCs=7; PSS start/peak MB=172/185; db_events=2802, packets_v2=0, batches_v1=40

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 16.9 | 23.2 | 0 |
| track_enqueue | 1.00 | 0.7 | 1.0 | 0 |
| persist_total | 0.02 | 163.4 | 688.6 | 0 |
| snapshot_batch | 0.02 | 0.1 | 0.1 | 0 |
| jni_enqueue_batch | 0.01 | 62.2 | 76.2 | 0 |
| uploader_flush | 0.02 | 99.7 | 610.7 | 0 |
| jni_get_state | 0.01 | 0.9 | 1.0 | 0 |
| jni_read_batch | 0.03 | 21.9 | 24.9 | 0 |
| jni_delete_ack | 0.01 | 11.3 | 16.7 | 0 |
| v1_parse_queued | 0.02 | 36.0 | 42.2 | 0 |
| v1_send_batch(json+gzip+http) | 0.02 | 24.1 | 519.7 | 0 |
| v1_gzip_body | 0.02 | 15.6 | 20.0 | 0 |
| http_send(wall) | 0.02 | 3.4 | 487.2 | 0 |

Traffic: V7 packets 0 (0 B), V1 batches 60 (gzip 445769 B, json 5654444 B) -> 159.2 B/event body; persist_calls=53 for 2800 events (avg 52.83 events per call)

## v1_perframe1

events=1200, scenario_ms=40062, process CPU: scenario 7808 µs/event, drain 17 µs/event, total 7825 µs/event; GC0/1/2=37/37/37; Track µs p50/p95/p99=36.4/81.1/158.9; frame ms p99=0.16; Unity main-thread GC alloc/event=28489 B (174.45 allocs); ART(Java) alloc/event=9523 B, ART GCs=3; PSS start/peak MB=166/179; db_events=1202, packets_v2=0, batches_v1=21

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 35.7 | 41.3 | 0 |
| track_enqueue | 1.00 | 5.2 | 5.8 | 0 |
| persist_total | 0.16 | 271.5 | 916.4 | 0 |
| snapshot_batch | 0.16 | 0.6 | 0.7 | 0 |
| jni_enqueue_batch | 0.16 | 190.8 | 327.8 | 0 |
| uploader_flush | 0.16 | 68.5 | 572.3 | 0 |
| jni_get_state | 0.01 | 0.6 | 2.8 | 0 |
| jni_read_batch | 0.03 | 13.8 | 22.1 | 0 |
| jni_delete_ack | 0.02 | 11.0 | 18.6 | 0 |
| v1_parse_queued | 0.02 | 19.6 | 23.0 | 0 |
| v1_send_batch(json+gzip+http) | 0.02 | 17.9 | 500.0 | 0 |
| v1_gzip_body | 0.02 | 9.2 | 9.5 | 0 |
| http_send(wall) | 0.02 | 3.8 | 482.0 | 0 |

Traffic: V7 packets 0 (0 B), V1 batches 19 (gzip 117012 B, json 1365351 B) -> 97.5 B/event body; persist_calls=187 for 1200 events (avg 6.42 events per call)

## v1_persec

events=90, scenario_ms=92959, process CPU: scenario 231444 µs/event, drain 0 µs/event, total 231444 µs/event; GC0/1/2=56/56/56; Track µs p50/p95/p99=64.5/116.2/359.3; frame ms p99=0.36; Unity main-thread GC alloc/event=135053 B (1107.61 allocs); ART(Java) alloc/event=34953 B, ART GCs=1; PSS start/peak MB=160/171; db_events=92, packets_v2=0, batches_v1=21

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 69.5 | 82.0 | 0 |
| track_enqueue | 1.00 | 32.5 | 38.3 | 0 |
| persist_total | 1.24 | 1648.6 | 4541.0 | 0 |
| snapshot_batch | 1.04 | 3.3 | 3.3 | 0 |
| jni_enqueue_batch | 1.00 | 1065.5 | 2153.7 | 0 |
| uploader_flush | 1.04 | 487.1 | 2267.3 | 0 |
| jni_get_state | 0.21 | 13.6 | 21.3 | 0 |
| jni_read_batch | 0.42 | 264.5 | 512.6 | 0 |
| jni_delete_ack | 0.21 | 53.2 | 148.9 | 0 |
| v1_parse_queued | 0.21 | 40.5 | 86.3 | 0 |
| v1_send_batch(json+gzip+http) | 0.21 | 99.2 | 1480.5 | 0 |
| v1_gzip_body | 0.21 | 20.9 | 20.9 | 0 |
| http_send(wall) | 0.21 | 59.5 | 1424.6 | 0 |

Traffic: V7 packets 0 (0 B), V1 batches 19 (gzip 22500 B, json 101229 B) -> 250.0 B/event body; persist_calls=112 for 90 events (avg 0.80 events per call)

## v1_single

events=15, scenario_ms=90494, process CPU: scenario 1344000 µs/event, drain 667 µs/event, total 1344667 µs/event; GC0/1/2=24/24/24; Track µs p50/p95/p99=63.2/85.4/85.4; frame ms p99=0.09; Unity main-thread GC alloc/event=313283 B (2759.47 allocs); ART(Java) alloc/event=58982 B, ART GCs=1; PSS start/peak MB=160/169; db_events=17, packets_v2=0, batches_v1=14

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 70.4 | 71.7 | 0 |
| track_enqueue | 1.00 | 26.8 | 26.7 | 0 |
| persist_total | 2.47 | 3506.4 | 9745.4 | 0 |
| snapshot_batch | 1.60 | 8.9 | 15.3 | 0 |
| jni_enqueue_batch | 1.00 | 1398.3 | 2323.7 | 0 |
| uploader_flush | 1.60 | 1911.9 | 7205.9 | 0 |
| jni_get_state | 1.07 | 175.9 | 219.7 | 0 |
| jni_read_batch | 1.87 | 1172.5 | 1720.9 | 0 |
| jni_delete_ack | 0.80 | 156.1 | 376.3 | 0 |
| v1_parse_queued | 0.80 | 62.7 | 90.4 | 0 |
| v1_send_batch(json+gzip+http) | 0.80 | 299.0 | 4750.3 | 0 |
| v1_gzip_body | 0.80 | 83.6 | 113.7 | 0 |
| http_send(wall) | 0.80 | 158.9 | 4525.9 | 0 |

Traffic: V7 packets 0 (0 B), V1 batches 12 (gzip 8661 B, json 17729 B) -> 577.4 B/event body; persist_calls=37 for 15 events (avg 0.41 events per call)

## v7_burst100

events=500, scenario_ms=60094, process CPU: scenario 26660 µs/event, drain 0 µs/event, total 26660 µs/event; GC0/1/2=9/9/9; Track µs p50/p95/p99=14.5/29.5/76.7; frame ms p99=1.65; Unity main-thread GC alloc/event=10697 B (76.99 allocs); ART(Java) alloc/event=6513 B, ART GCs=1; PSS start/peak MB=162/176; db_events=502, packets_v2=7, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 20.2 | 24.7 | 0 |
| track_enqueue | 1.00 | 0.6 | 0.8 | 0 |
| persist_total | 0.04 | 147.0 | 610.9 | 0 |
| snapshot_batch | 0.03 | 0.1 | 0.3 | 0 |
| jni_enqueue_batch | 0.01 | 74.7 | 112.5 | 0 |
| uploader_flush | 0.03 | 68.9 | 494.0 | 0 |
| jni_get_state | 0.02 | 2.5 | 2.7 | 0 |
| jni_read_batch | 0.03 | 19.3 | 22.7 | 0 |
| jni_delete_ack | 0.01 | 3.8 | 4.5 | 0 |
| v7_encode(parse+pack+zstd) | 0.01 | 31.9 | 42.2 | 0 |
| v7_post_packet | 0.01 | 3.6 | 413.7 | 0 |

Traffic: V7 packets 5 (9704 B), V1 batches 0 (gzip 0 B, json 0 B) -> 19.4 B/event body; persist_calls=20 for 500 events (avg 25.00 events per call)

## v7_burst20f

events=2800, scenario_ms=4665, process CPU: scenario 507 µs/event, drain 3518 µs/event, total 4025 µs/event; GC0/1/2=11/11/11; Track µs p50/p95/p99=14.9/35.7/115.7; frame ms p99=2.14; Unity main-thread GC alloc/event=12521 B (86.90 allocs); ART(Java) alloc/event=8691 B, ART GCs=6; PSS start/peak MB=173/189; db_events=2802, packets_v2=40, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 16.8 | 21.0 | 0 |
| track_enqueue | 1.00 | 0.9 | 2.6 | 0 |
| persist_total | 0.02 | 159.0 | 672.3 | 0 |
| snapshot_batch | 0.02 | 0.2 | 0.2 | 0 |
| jni_enqueue_batch | 0.01 | 67.3 | 94.8 | 0 |
| uploader_flush | 0.02 | 90.1 | 575.6 | 0 |
| jni_get_state | 0.01 | 1.0 | 1.0 | 0 |
| jni_read_batch | 0.03 | 18.1 | 22.6 | 0 |
| jni_delete_ack | 0.01 | 5.1 | 8.5 | 0 |
| v7_encode(parse+pack+zstd) | 0.02 | 54.8 | 65.6 | 0 |
| v7_post_packet | 0.02 | 6.0 | 471.3 | 0 |

Traffic: V7 packets 60 (102653 B), V1 batches 0 (gzip 0 B, json 0 B) -> 36.7 B/event body; persist_calls=53 for 2800 events (avg 52.83 events per call)

## v7_perframe1

events=1200, scenario_ms=40031, process CPU: scenario 8283 µs/event, drain 8 µs/event, total 8292 µs/event; GC0/1/2=25/25/25; Track µs p50/p95/p99=36.5/75.5/150.9; frame ms p99=0.15; Unity main-thread GC alloc/event=19328 B (157.09 allocs); ART(Java) alloc/event=8912 B, ART GCs=3; PSS start/peak MB=165/179; db_events=1202, packets_v2=21, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 39.1 | 47.6 | 0 |
| track_enqueue | 1.00 | 9.0 | 9.8 | 0 |
| persist_total | 0.15 | 268.0 | 904.3 | 0 |
| snapshot_batch | 0.15 | 0.6 | 1.3 | 0 |
| jni_enqueue_batch | 0.15 | 192.7 | 373.8 | 0 |
| uploader_flush | 0.15 | 62.7 | 511.7 | 0 |
| jni_get_state | 0.01 | 0.8 | 4.5 | 0 |
| jni_read_batch | 0.03 | 16.7 | 20.8 | 0 |
| jni_delete_ack | 0.02 | 4.1 | 4.2 | 0 |
| v7_encode(parse+pack+zstd) | 0.02 | 31.0 | 34.7 | 0 |
| v7_post_packet | 0.02 | 4.9 | 442.1 | 0 |

Traffic: V7 packets 19 (26621 B), V1 batches 0 (gzip 0 B, json 0 B) -> 22.2 B/event body; persist_calls=186 for 1200 events (avg 6.45 events per call)

## v7_persec

events=90, scenario_ms=92959, process CPU: scenario 231556 µs/event, drain 222 µs/event, total 231778 µs/event; GC0/1/2=45/45/45; Track µs p50/p95/p99=64.3/123.2/132.2; frame ms p99=0.13; Unity main-thread GC alloc/event=126019 B (1160.56 allocs); ART(Java) alloc/event=40050 B, ART GCs=1; PSS start/peak MB=159/172; db_events=92, packets_v2=21, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 61.5 | 70.3 | 0 |
| track_enqueue | 1.00 | 22.5 | 25.7 | 0 |
| persist_total | 1.23 | 1575.9 | 4684.8 | 0 |
| snapshot_batch | 1.01 | 3.4 | 3.9 | 0 |
| jni_enqueue_batch | 1.00 | 924.1 | 2291.5 | 0 |
| uploader_flush | 1.01 | 565.0 | 2289.6 | 0 |
| jni_get_state | 0.21 | 12.6 | 18.0 | 0 |
| jni_read_batch | 0.42 | 295.1 | 430.4 | 0 |
| jni_delete_ack | 0.21 | 40.6 | 76.9 | 0 |
| v7_encode(parse+pack+zstd) | 0.21 | 57.2 | 182.9 | 0 |
| v7_post_packet | 0.21 | 83.8 | 1491.8 | 0 |

Traffic: V7 packets 19 (5638 B), V1 batches 0 (gzip 0 B, json 0 B) -> 62.6 B/event body; persist_calls=111 for 90 events (avg 0.81 events per call)

## v7_single

events=15, scenario_ms=90357, process CPU: scenario 1337333 µs/event, drain 1333 µs/event, total 1338667 µs/event; GC0/1/2=21/21/21; Track µs p50/p95/p99=65.6/149.7/149.7; frame ms p99=0.15; Unity main-thread GC alloc/event=316720 B (3056.40 allocs); ART(Java) alloc/event=56798 B, ART GCs=1; PSS start/peak MB=161/172; db_events=17, packets_v2=14, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 73.5 | 78.5 | 0 |
| track_enqueue | 1.00 | 27.9 | 28.4 | 0 |
| persist_total | 2.47 | 3968.7 | 10915.3 | 0 |
| snapshot_batch | 1.60 | 6.7 | 7.1 | 0 |
| jni_enqueue_batch | 1.00 | 1281.3 | 2886.7 | 0 |
| uploader_flush | 1.60 | 2472.0 | 7798.0 | 0 |
| jni_get_state | 1.07 | 87.8 | 87.5 | 0 |
| jni_read_batch | 1.87 | 1224.6 | 2348.4 | 0 |
| jni_delete_ack | 0.80 | 318.8 | 380.7 | 0 |
| v7_encode(parse+pack+zstd) | 0.80 | 82.6 | 82.5 | 0 |
| v7_post_packet | 0.80 | 320.6 | 4448.7 | 0 |

Traffic: V7 packets 12 (2060 B), V1 batches 0 (gzip 0 B, json 0 B) -> 137.3 B/event body; persist_calls=37 for 15 events (avg 0.41 events per call)
