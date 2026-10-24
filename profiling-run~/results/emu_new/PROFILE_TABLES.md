# Profiling tables (emu_new)

Per event = stage total / events in scenario. Times in µs. cpu = thread CPU, wall = elapsed incl. blocking. Stages nest (inclusive).


## none_burst20f

events=2800, scenario_ms=4662, process CPU: scenario 525 µs/event, drain 0 µs/event, total 525 µs/event; GC0/1/2=0/0/0; Track µs p50/p95/p99=0.0/0.1/0.3; frame ms p99=0.02; Unity main-thread GC alloc/event=280 B (3.29 allocs); ART(Java) alloc/event=35 B, ART GCs=0; PSS start/peak MB=172/174; db_events=0, packets_v2=0, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|

Traffic: V7 packets 0 (0 B), V1 batches 0 (gzip 0 B, json 0 B) -> 0.0 B/event body; persist_calls=None for 2800 events (avg 0.00 events per call)

## none_perframe1

events=1200, scenario_ms=40092, process CPU: scenario 7692 µs/event, drain 0 µs/event, total 7692 µs/event; GC0/1/2=0/0/0; Track µs p50/p95/p99=0.2/0.4/0.5; frame ms p99=0.01; Unity main-thread GC alloc/event=646 B (7.38 allocs); ART(Java) alloc/event=55 B, ART GCs=1; PSS start/peak MB=165/168; db_events=0, packets_v2=0, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|

Traffic: V7 packets 0 (0 B), V1 batches 0 (gzip 0 B, json 0 B) -> 0.0 B/event body; persist_calls=None for 1200 events (avg 0.00 events per call)

## v1_burst100

events=500, scenario_ms=60127, process CPU: scenario 27260 µs/event, drain 40 µs/event, total 27300 µs/event; GC0/1/2=18/18/18; Track µs p50/p95/p99=23.0/31.4/87.9; frame ms p99=2.58; Unity main-thread GC alloc/event=19732 B (94.56 allocs); ART(Java) alloc/event=7299 B, ART GCs=1; PSS start/peak MB=162/173; db_events=502, packets_v2=0, batches_v1=7

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 24.3 | 25.5 | 0 |
| track_enqueue | 1.00 | 0.7 | 0.8 | 0 |
| persist_total | 0.04 | 159.3 | 745.5 | 0 |
| snapshot_batch | 0.04 | 0.1 | 0.2 | 0 |
| jni_enqueue_batch | 0.01 | 66.7 | 109.6 | 0 |
| uploader_flush | 0.04 | 88.1 | 629.5 | 0 |
| jni_get_state | 0.02 | 1.7 | 1.8 | 0 |
| jni_read_batch | 0.03 | 33.6 | 38.6 | 0 |
| jni_delete_ack | 0.01 | 10.2 | 10.8 | 0 |
| v1_parse_queued | 0.01 | 20.4 | 22.7 | 0 |
| v1_send_batch(json+gzip+http) | 0.01 | 14.1 | 541.4 | 0 |
| v1_gzip_body | 0.01 | 8.5 | 14.8 | 0 |
| http_send(wall) | 0.01 | 1.6 | 513.1 | 0 |

Traffic: V7 packets 0 (0 B), V1 batches 5 (gzip 43235 B, json 563349 B) -> 86.5 B/event body; persist_calls=20 for 500 events (avg 25.00 events per call)

## v1_burst20f

events=2800, scenario_ms=4664, process CPU: scenario 525 µs/event, drain 4032 µs/event, total 4557 µs/event; GC0/1/2=20/20/20; Track µs p50/p95/p99=22.6/45.3/88.2; frame ms p99=3.93; Unity main-thread GC alloc/event=28822 B (120.52 allocs); ART(Java) alloc/event=9536 B, ART GCs=7; PSS start/peak MB=172/186; db_events=2802, packets_v2=0, batches_v1=41

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 25.3 | 31.0 | 0 |
| track_enqueue | 1.00 | 0.9 | 2.5 | 0 |
| persist_total | 0.02 | 168.5 | 666.0 | 0 |
| snapshot_batch | 0.02 | 0.1 | 0.1 | 0 |
| jni_enqueue_batch | 0.01 | 63.6 | 82.2 | 0 |
| uploader_flush | 0.02 | 103.1 | 581.0 | 0 |
| jni_get_state | 0.01 | 1.0 | 1.0 | 0 |
| jni_read_batch | 0.03 | 21.7 | 24.5 | 0 |
| jni_delete_ack | 0.01 | 10.8 | 18.5 | 0 |
| v1_parse_queued | 0.02 | 37.8 | 45.9 | 0 |
| v1_send_batch(json+gzip+http) | 0.02 | 25.1 | 481.5 | 0 |
| v1_gzip_body | 0.02 | 16.7 | 19.2 | 0 |
| http_send(wall) | 0.02 | 3.4 | 452.9 | 0 |

Traffic: V7 packets 0 (0 B), V1 batches 64 (gzip 451712 B, json 5705823 B) -> 161.3 B/event body; persist_calls=60 for 2800 events (avg 46.67 events per call)

## v1_perframe1

events=1200, scenario_ms=40100, process CPU: scenario 7892 µs/event, drain 17 µs/event, total 7908 µs/event; GC0/1/2=37/37/37; Track µs p50/p95/p99=48.2/94.2/152.7; frame ms p99=0.15; Unity main-thread GC alloc/event=28216 B (171.84 allocs); ART(Java) alloc/event=9571 B, ART GCs=4; PSS start/peak MB=165/178; db_events=1202, packets_v2=0, batches_v1=19

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 47.0 | 53.2 | 0 |
| track_enqueue | 1.00 | 5.4 | 6.2 | 0 |
| persist_total | 0.16 | 277.6 | 889.1 | 0 |
| snapshot_batch | 0.16 | 0.8 | 1.3 | 0 |
| jni_enqueue_batch | 0.15 | 194.2 | 358.3 | 0 |
| uploader_flush | 0.16 | 70.3 | 514.8 | 0 |
| jni_get_state | 0.01 | 0.5 | 0.7 | 0 |
| jni_read_batch | 0.02 | 13.5 | 15.6 | 0 |
| jni_delete_ack | 0.01 | 10.4 | 15.1 | 0 |
| v1_parse_queued | 0.01 | 24.9 | 39.6 | 0 |
| v1_send_batch(json+gzip+http) | 0.01 | 15.1 | 437.8 | 0 |
| v1_gzip_body | 0.01 | 9.6 | 10.4 | 0 |
| http_send(wall) | 0.01 | 2.4 | 415.6 | 0 |

Traffic: V7 packets 0 (0 B), V1 batches 17 (gzip 116056 B, json 1364931 B) -> 96.7 B/event body; persist_calls=189 for 1200 events (avg 6.35 events per call)

## v1_persec

events=90, scenario_ms=92995, process CPU: scenario 231889 µs/event, drain 333 µs/event, total 232222 µs/event; GC0/1/2=56/56/56; Track µs p50/p95/p99=69.8/120.5/143.3; frame ms p99=0.14; Unity main-thread GC alloc/event=134404 B (1106.79 allocs); ART(Java) alloc/event=42234 B, ART GCs=1; PSS start/peak MB=160/170; db_events=92, packets_v2=0, batches_v1=21

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 68.2 | 73.8 | 0 |
| track_enqueue | 1.00 | 20.4 | 20.8 | 0 |
| persist_total | 1.26 | 1567.5 | 4712.7 | 0 |
| snapshot_batch | 1.26 | 3.8 | 3.7 | 0 |
| jni_enqueue_batch | 1.00 | 994.7 | 2212.2 | 0 |
| uploader_flush | 1.26 | 465.9 | 2366.5 | 0 |
| jni_get_state | 0.21 | 10.6 | 11.2 | 0 |
| jni_read_batch | 0.42 | 237.1 | 401.9 | 0 |
| jni_delete_ack | 0.21 | 50.4 | 87.7 | 0 |
| v1_parse_queued | 0.21 | 28.9 | 32.8 | 0 |
| v1_send_batch(json+gzip+http) | 0.21 | 122.8 | 1814.8 | 0 |
| v1_gzip_body | 0.21 | 26.1 | 41.8 | 0 |
| http_send(wall) | 0.21 | 42.2 | 1492.1 | 0 |

Traffic: V7 packets 0 (0 B), V1 batches 19 (gzip 22552 B, json 101229 B) -> 250.6 B/event body; persist_calls=113 for 90 events (avg 0.80 events per call)

## v1_single

events=15, scenario_ms=90493, process CPU: scenario 1334000 µs/event, drain 0 µs/event, total 1334000 µs/event; GC0/1/2=25/25/25; Track µs p50/p95/p99=67.6/80.1/80.1; frame ms p99=0.08; Unity main-thread GC alloc/event=311162 B (2761.00 allocs); ART(Java) alloc/event=87381 B, ART GCs=1; PSS start/peak MB=160/168; db_events=17, packets_v2=0, batches_v1=14

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 69.3 | 70.5 | 0 |
| track_enqueue | 1.00 | 23.6 | 23.3 | 0 |
| persist_total | 2.53 | 3061.5 | 9272.3 | 0 |
| snapshot_batch | 2.53 | 5.9 | 6.1 | 0 |
| jni_enqueue_batch | 1.00 | 1112.5 | 1863.3 | 0 |
| uploader_flush | 2.53 | 1718.3 | 7173.4 | 0 |
| jni_get_state | 1.07 | 65.6 | 74.9 | 0 |
| jni_read_batch | 1.87 | 1044.9 | 2295.7 | 0 |
| jni_delete_ack | 0.80 | 153.1 | 168.7 | 0 |
| v1_parse_queued | 0.80 | 62.5 | 98.1 | 0 |
| v1_send_batch(json+gzip+http) | 0.80 | 330.9 | 4453.9 | 0 |
| v1_gzip_body | 0.80 | 109.8 | 535.1 | 0 |
| http_send(wall) | 0.80 | 173.3 | 3840.7 | 0 |

Traffic: V7 packets 0 (0 B), V1 batches 12 (gzip 8762 B, json 17729 B) -> 584.1 B/event body; persist_calls=38 for 15 events (avg 0.39 events per call)

## v7_burst100

events=500, scenario_ms=60153, process CPU: scenario 26060 µs/event, drain 20 µs/event, total 26080 µs/event; GC0/1/2=13/13/13; Track µs p50/p95/p99=22.0/31.1/74.2; frame ms p99=2.57; Unity main-thread GC alloc/event=13785 B (113.62 allocs); ART(Java) alloc/event=6840 B, ART GCs=1; PSS start/peak MB=162/176; db_events=502, packets_v2=7, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 24.6 | 28.3 | 0 |
| track_enqueue | 1.00 | 0.7 | 0.7 | 0 |
| persist_total | 0.04 | 156.0 | 614.5 | 0 |
| snapshot_batch | 0.04 | 0.1 | 0.2 | 0 |
| jni_enqueue_batch | 0.01 | 77.0 | 105.4 | 0 |
| uploader_flush | 0.04 | 73.9 | 499.1 | 0 |
| jni_get_state | 0.02 | 1.8 | 2.3 | 0 |
| jni_read_batch | 0.03 | 20.5 | 38.5 | 0 |
| jni_delete_ack | 0.01 | 3.8 | 11.6 | 0 |
| v7_encode(parse+pack+zstd) | 0.01 | 34.3 | 41.3 | 0 |
| v7_post_packet | 0.01 | 5.1 | 396.3 | 0 |

Traffic: V7 packets 5 (9737 B), V1 batches 0 (gzip 0 B, json 0 B) -> 19.5 B/event body; persist_calls=20 for 500 events (avg 25.00 events per call)

## v7_burst20f

events=2800, scenario_ms=4663, process CPU: scenario 639 µs/event, drain 5682 µs/event, total 6321 µs/event; GC0/1/2=14/14/14; Track µs p50/p95/p99=22.9/47.8/114.4; frame ms p99=2.57; Unity main-thread GC alloc/event=18059 B (152.82 allocs); ART(Java) alloc/event=8950 B, ART GCs=7; PSS start/peak MB=173/188; db_events=2802, packets_v2=41, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 28.0 | 31.0 | 0 |
| track_enqueue | 1.00 | 2.4 | 2.8 | 0 |
| persist_total | 0.02 | 175.3 | 686.1 | 0 |
| snapshot_batch | 0.02 | 0.1 | 0.1 | 0 |
| jni_enqueue_batch | 0.01 | 67.0 | 96.1 | 0 |
| uploader_flush | 0.02 | 106.5 | 587.7 | 0 |
| jni_get_state | 0.01 | 1.0 | 1.0 | 0 |
| jni_read_batch | 0.03 | 27.9 | 32.7 | 0 |
| jni_delete_ack | 0.01 | 5.6 | 11.2 | 0 |
| v7_encode(parse+pack+zstd) | 0.02 | 59.6 | 76.7 | 0 |
| v7_post_packet | 0.02 | 6.3 | 458.2 | 0 |

Traffic: V7 packets 64 (105287 B), V1 batches 0 (gzip 0 B, json 0 B) -> 37.6 B/event body; persist_calls=57 for 2800 events (avg 49.12 events per call)

## v7_perframe1

events=1200, scenario_ms=40029, process CPU: scenario 9858 µs/event, drain 25 µs/event, total 9883 µs/event; GC0/1/2=29/29/29; Track µs p50/p95/p99=45.4/95.0/172.3; frame ms p99=0.18; Unity main-thread GC alloc/event=21804 B (188.93 allocs); ART(Java) alloc/event=9018 B, ART GCs=3; PSS start/peak MB=165/178; db_events=1202, packets_v2=22, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 47.3 | 54.0 | 0 |
| track_enqueue | 1.00 | 5.0 | 5.6 | 0 |
| persist_total | 0.16 | 280.7 | 931.1 | 0 |
| snapshot_batch | 0.16 | 0.5 | 1.1 | 0 |
| jni_enqueue_batch | 0.16 | 201.3 | 410.3 | 0 |
| uploader_flush | 0.16 | 68.0 | 503.3 | 0 |
| jni_get_state | 0.01 | 0.4 | 0.5 | 0 |
| jni_read_batch | 0.03 | 13.0 | 14.3 | 0 |
| jni_delete_ack | 0.02 | 4.2 | 5.2 | 0 |
| v7_encode(parse+pack+zstd) | 0.02 | 37.6 | 55.9 | 0 |
| v7_post_packet | 0.02 | 5.0 | 418.8 | 0 |

Traffic: V7 packets 20 (26694 B), V1 batches 0 (gzip 0 B, json 0 B) -> 22.2 B/event body; persist_calls=189 for 1200 events (avg 6.35 events per call)

## v7_persec

events=90, scenario_ms=93024, process CPU: scenario 238111 µs/event, drain 111 µs/event, total 238222 µs/event; GC0/1/2=47/47/47; Track µs p50/p95/p99=70.6/108.6/241.6; frame ms p99=0.24; Unity main-thread GC alloc/event=128362 B (1193.94 allocs); ART(Java) alloc/event=47696 B, ART GCs=1; PSS start/peak MB=160/173; db_events=92, packets_v2=21, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 70.4 | 78.4 | 0 |
| track_enqueue | 1.00 | 22.5 | 25.2 | 0 |
| persist_total | 1.23 | 1770.4 | 4600.0 | 0 |
| snapshot_batch | 1.23 | 3.8 | 5.0 | 0 |
| jni_enqueue_batch | 1.00 | 1013.5 | 1992.2 | 0 |
| uploader_flush | 1.23 | 604.8 | 2435.1 | 0 |
| jni_get_state | 0.21 | 11.1 | 12.0 | 0 |
| jni_read_batch | 0.42 | 264.7 | 500.3 | 0 |
| jni_delete_ack | 0.21 | 42.2 | 57.6 | 0 |
| v7_encode(parse+pack+zstd) | 0.21 | 61.4 | 110.2 | 0 |
| v7_post_packet | 0.21 | 135.0 | 1625.8 | 0 |

Traffic: V7 packets 19 (5644 B), V1 batches 0 (gzip 0 B, json 0 B) -> 62.7 B/event body; persist_calls=111 for 90 events (avg 0.81 events per call)

## v7_single

events=15, scenario_ms=90425, process CPU: scenario 1347333 µs/event, drain 667 µs/event, total 1348000 µs/event; GC0/1/2=21/21/21; Track µs p50/p95/p99=71.3/147.9/147.9; frame ms p99=0.15; Unity main-thread GC alloc/event=317521 B (3084.80 allocs); ART(Java) alloc/event=87381 B, ART GCs=1; PSS start/peak MB=161/172; db_events=17, packets_v2=14, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 75.6 | 89.6 | 0 |
| track_enqueue | 1.00 | 21.9 | 23.4 | 0 |
| persist_total | 2.47 | 4132.7 | 23892.0 | 0 |
| snapshot_batch | 2.47 | 5.1 | 6.8 | 0 |
| jni_enqueue_batch | 1.00 | 1499.9 | 10564.7 | 0 |
| uploader_flush | 2.47 | 2388.6 | 12813.5 | 0 |
| jni_get_state | 1.07 | 65.0 | 91.2 | 0 |
| jni_read_batch | 1.87 | 987.1 | 1860.3 | 0 |
| jni_delete_ack | 0.80 | 189.4 | 220.9 | 0 |
| v7_encode(parse+pack+zstd) | 0.80 | 103.3 | 132.7 | 0 |
| v7_post_packet | 0.80 | 628.3 | 9790.1 | 0 |

Traffic: V7 packets 12 (2059 B), V1 batches 0 (gzip 0 B, json 0 B) -> 137.3 B/event body; persist_calls=37 for 15 events (avg 0.41 events per call)
