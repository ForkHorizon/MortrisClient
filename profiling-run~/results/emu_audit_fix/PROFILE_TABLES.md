# Profiling tables (emu_audit_fix)

Per event = stage total / events in scenario. Times in µs. cpu = thread CPU, wall = elapsed incl. blocking. Stages nest (inclusive).


## none_burst20f

events=2800, scenario_ms=4668, process CPU: scenario 393 µs/event, drain 0 µs/event, total 393 µs/event; GC0/1/2=0/0/0; Track µs p50/p95/p99=0.0/0.1/0.3; frame ms p99=0.05; Unity main-thread GC alloc/event=287 B (3.36 allocs); ART(Java) alloc/event=12 B, ART GCs=0; PSS start/peak MB=174/176; db_events=0, packets_v2=0, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|

Traffic: V7 packets 0 (0 B), V1 batches 0 (gzip 0 B, json 0 B) -> 0.0 B/event body; persist_calls=None for 2800 events (avg 0.00 events per call)

## none_perframe1

events=1200, scenario_ms=40097, process CPU: scenario 7950 µs/event, drain 0 µs/event, total 7950 µs/event; GC0/1/2=0/0/0; Track µs p50/p95/p99=0.3/0.4/0.5; frame ms p99=0.01; Unity main-thread GC alloc/event=647 B (7.38 allocs); ART(Java) alloc/event=55 B, ART GCs=1; PSS start/peak MB=165/168; db_events=0, packets_v2=0, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|

Traffic: V7 packets 0 (0 B), V1 batches 0 (gzip 0 B, json 0 B) -> 0.0 B/event body; persist_calls=None for 1200 events (avg 0.00 events per call)

## v1_burst100

events=500, scenario_ms=60162, process CPU: scenario 27960 µs/event, drain 20 µs/event, total 27980 µs/event; GC0/1/2=16/16/16; Track µs p50/p95/p99=14.9/20.6/69.4; frame ms p99=1.74; Unity main-thread GC alloc/event=16884 B (70.20 allocs); ART(Java) alloc/event=6906 B, ART GCs=1; PSS start/peak MB=162/173; db_events=502, packets_v2=0, batches_v1=7

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 16.7 | 17.9 | 492 |
| track_enqueue | 1.00 | 0.7 | 0.9 | 483 |
| persist_total | 0.04 | 120.5 | 584.4 | 2212 |
| snapshot_batch | 0.03 | 0.2 | 0.2 | 803 |
| jni_enqueue_batch | 0.01 | 55.0 | 70.3 | 0 |
| uploader_flush | 0.03 | 62.2 | 509.9 | 1778 |
| jni_get_state | 0.03 | 2.0 | 2.0 | 0 |
| jni_read_batch | 0.03 | 5.7 | 5.7 | 827 |
| jni_delete_ack | 0.01 | 9.3 | 9.8 | 0 |
| v1_parse_queued | 0.01 | 25.7 | 32.0 | 1696 |
| v1_send_batch(json+gzip+http) | 0.01 | 14.1 | 454.9 | 3088 |
| v1_gzip_body | 0.01 | 7.8 | 9.1 | 778 |
| http_send(wall) | 0.01 | 1.9 | 398.6 | 516 |

Traffic: V7 packets 0 (0 B), V1 batches 5 (gzip 43240 B, json 562849 B) -> 86.5 B/event body; persist_calls=20 for 500 events (avg 25.00 events per call)

## v1_burst20f

events=2800, scenario_ms=4664, process CPU: scenario 507 µs/event, drain 14 µs/event, total 521 µs/event; GC0/1/2=22/22/22; Track µs p50/p95/p99=14.6/38.4/75.2; frame ms p99=3.57; Unity main-thread GC alloc/event=15493 B (57.98 allocs); ART(Java) alloc/event=6355 B, ART GCs=4; PSS start/peak MB=175/184; db_events=2802, packets_v2=0, batches_v1=30

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 19.1 | 23.0 | 453 |
| track_enqueue | 1.00 | 0.8 | 1.1 | 167 |
| persist_total | 0.01 | 119.8 | 571.1 | 3632 |
| snapshot_batch | 0.01 | 0.1 | 0.1 | 806 |
| jni_enqueue_batch | 0.01 | 65.4 | 76.4 | 25 |
| uploader_flush | 0.01 | 53.7 | 493.7 | 4168 |
| jni_get_state | 0.01 | 0.5 | 0.5 | 0 |
| jni_read_batch | 0.01 | 3.8 | 4.0 | 816 |
| jni_delete_ack | 0.01 | 10.6 | 15.9 | 0 |
| v1_parse_queued | 0.01 | 20.1 | 21.9 | 3868 |
| v1_send_batch(json+gzip+http) | 0.01 | 13.0 | 445.4 | 3939 |
| v1_gzip_body | 0.01 | 8.7 | 9.7 | 669 |
| http_send(wall) | 0.01 | 1.7 | 430.6 | 455 |

Traffic: V7 packets 0 (0 B), V1 batches 28 (gzip 246140 B, json 3198038 B) -> 87.9 B/event body; persist_calls=23 for 2800 events (avg 121.74 events per call)

## v1_perframe1

events=1200, scenario_ms=40062, process CPU: scenario 7725 µs/event, drain 8 µs/event, total 7742 µs/event; GC0/1/2=19/19/19; Track µs p50/p95/p99=41.7/71.0/135.0; frame ms p99=0.14; Unity main-thread GC alloc/event=15854 B (64.86 allocs); ART(Java) alloc/event=9564 B, ART GCs=3; PSS start/peak MB=166/177; db_events=1202, packets_v2=0, batches_v1=15

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 40.9 | 50.0 | 44 |
| track_enqueue | 1.00 | 5.6 | 6.0 | 14 |
| persist_total | 0.16 | 157.0 | 669.9 | 6403 |
| snapshot_batch | 0.16 | 0.6 | 0.7 | 1212 |
| jni_enqueue_batch | 0.16 | 79.4 | 162.4 | 3 |
| uploader_flush | 0.16 | 62.8 | 489.3 | 5212 |
| jni_get_state | 0.01 | 0.7 | 0.8 | 0 |
| jni_read_batch | 0.01 | 4.6 | 6.6 | 775 |
| jni_delete_ack | 0.01 | 8.9 | 9.7 | 0 |
| v1_parse_queued | 0.01 | 28.5 | 40.6 | 3065 |
| v1_send_batch(json+gzip+http) | 0.01 | 14.2 | 425.7 | 3642 |
| v1_gzip_body | 0.01 | 8.6 | 8.9 | 785 |
| http_send(wall) | 0.01 | 1.8 | 409.1 | 382 |

Traffic: V7 packets 0 (0 B), V1 batches 13 (gzip 113068 B, json 1362885 B) -> 94.2 B/event body; persist_calls=189 for 1200 events (avg 6.35 events per call)

## v1_persec

events=90, scenario_ms=92959, process CPU: scenario 239444 µs/event, drain 0 µs/event, total 239444 µs/event; GC0/1/2=15/15/15; Track µs p50/p95/p99=65.4/104.1/247.9; frame ms p99=0.25; Unity main-thread GC alloc/event=39893 B (289.70 allocs); ART(Java) alloc/event=35317 B, ART GCs=1; PSS start/peak MB=160/171; db_events=92, packets_v2=0, batches_v1=21

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 86.0 | 90.4 | 0 |
| track_enqueue | 1.00 | 21.5 | 22.0 | 0 |
| persist_total | 1.24 | 585.4 | 2477.4 | 12652 |
| snapshot_batch | 1.04 | 2.9 | 5.5 | 683 |
| jni_enqueue_batch | 1.00 | 236.4 | 466.4 | 0 |
| uploader_flush | 1.04 | 252.7 | 1881.4 | 11833 |
| jni_get_state | 0.21 | 18.2 | 39.1 | 0 |
| jni_read_batch | 0.22 | 22.3 | 24.6 | 910 |
| jni_delete_ack | 0.21 | 56.4 | 91.3 | 0 |
| v1_parse_queued | 0.21 | 46.9 | 192.1 | 6554 |
| v1_send_batch(json+gzip+http) | 0.21 | 93.1 | 1517.5 | 10468 |
| v1_gzip_body | 0.21 | 32.7 | 57.8 | 4551 |
| http_send(wall) | 0.21 | 36.0 | 1421.7 | 4551 |

Traffic: V7 packets 0 (0 B), V1 batches 19 (gzip 22542 B, json 101139 B) -> 250.5 B/event body; persist_calls=112 for 90 events (avg 0.80 events per call)

## v1_single

events=15, scenario_ms=90494, process CPU: scenario 1374000 µs/event, drain 0 µs/event, total 1374667 µs/event; GC0/1/2=8/8/8; Track µs p50/p95/p99=68.5/131.3/131.3; frame ms p99=0.13; Unity main-thread GC alloc/event=122099 B (1125.53 allocs); ART(Java) alloc/event=56798 B, ART GCs=1; PSS start/peak MB=161/171; db_events=17, packets_v2=0, batches_v1=14

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 69.1 | 79.9 | 0 |
| track_enqueue | 1.00 | 28.3 | 33.3 | 0 |
| persist_total | 2.53 | 1330.9 | 5979.7 | 29491 |
| snapshot_batch | 1.53 | 4.1 | 4.3 | 0 |
| jni_enqueue_batch | 1.00 | 233.6 | 263.1 | 0 |
| uploader_flush | 1.53 | 923.8 | 5441.8 | 27853 |
| jni_get_state | 1.07 | 80.9 | 89.5 | 0 |
| jni_read_batch | 1.07 | 110.3 | 113.9 | 0 |
| jni_delete_ack | 0.80 | 156.9 | 222.3 | 0 |
| v1_parse_queued | 0.80 | 61.1 | 75.0 | 7646 |
| v1_send_batch(json+gzip+http) | 0.80 | 476.0 | 4900.0 | 25395 |
| v1_gzip_body | 0.80 | 94.8 | 371.9 | 19661 |
| http_send(wall) | 0.80 | 168.6 | 4212.0 | 12015 |

Traffic: V7 packets 0 (0 B), V1 batches 12 (gzip 8720 B, json 17714 B) -> 581.3 B/event body; persist_calls=38 for 15 events (avg 0.39 events per call)

## v7_burst100

events=500, scenario_ms=60158, process CPU: scenario 27220 µs/event, drain 20 µs/event, total 27240 µs/event; GC0/1/2=7/7/7; Track µs p50/p95/p99=14.2/19.9/71.2; frame ms p99=1.97; Unity main-thread GC alloc/event=7653 B (50.87 allocs); ART(Java) alloc/event=6119 B, ART GCs=1; PSS start/peak MB=162/175; db_events=502, packets_v2=6, batches_v1=1

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 22.0 | 23.3 | 516 |
| track_enqueue | 1.00 | 0.7 | 0.8 | 483 |
| persist_total | 0.04 | 118.5 | 499.5 | 2425 |
| snapshot_batch | 0.03 | 0.1 | 0.2 | 803 |
| jni_enqueue_batch | 0.01 | 62.0 | 69.0 | 0 |
| uploader_flush | 0.03 | 51.6 | 425.0 | 1761 |
| jni_get_state | 0.02 | 1.9 | 1.9 | 0 |
| jni_read_batch | 0.02 | 3.9 | 3.9 | 827 |
| jni_delete_ack | 0.01 | 4.8 | 8.8 | 0 |
| v7_encode(parse+pack+zstd) | 0.01 | 31.0 | 35.1 | 836 |
| v7_post_packet | 0.01 | 4.1 | 369.3 | 344 |

Traffic: V7 packets 5 (9710 B), V1 batches 0 (gzip 0 B, json 0 B) -> 19.4 B/event body; persist_calls=19 for 500 events (avg 26.32 events per call)

## v7_burst20f

events=2800, scenario_ms=4696, process CPU: scenario 504 µs/event, drain 164 µs/event, total 668 µs/event; GC0/1/2=9/9/9; Track µs p50/p95/p99=14.8/36.7/82.9; frame ms p99=0.64; Unity main-thread GC alloc/event=6164 B (38.13 allocs); ART(Java) alloc/event=5710 B, ART GCs=4; PSS start/peak MB=174/187; db_events=2802, packets_v2=29, batches_v1=1

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 16.3 | 17.5 | 524 |
| track_enqueue | 1.00 | 0.8 | 1.1 | 161 |
| persist_total | 0.01 | 97.5 | 506.4 | 2642 |
| snapshot_batch | 0.01 | 0.1 | 0.2 | 805 |
| jni_enqueue_batch | 0.01 | 55.3 | 63.0 | 4 |
| uploader_flush | 0.01 | 41.3 | 442.5 | 2143 |
| jni_get_state | 0.01 | 0.5 | 0.5 | 3 |
| jni_read_batch | 0.01 | 3.3 | 5.8 | 805 |
| jni_delete_ack | 0.01 | 4.5 | 8.6 | 0 |
| v7_encode(parse+pack+zstd) | 0.01 | 27.0 | 29.0 | 2213 |
| v7_post_packet | 0.01 | 3.5 | 395.7 | 287 |

Traffic: V7 packets 28 (56383 B), V1 batches 0 (gzip 0 B, json 0 B) -> 20.1 B/event body; persist_calls=24 for 2800 events (avg 116.67 events per call)

## v7_perframe1

events=1200, scenario_ms=40063, process CPU: scenario 7700 µs/event, drain 0 µs/event, total 7700 µs/event; GC0/1/2=9/9/9; Track µs p50/p95/p99=41.9/74.5/175.5; frame ms p99=0.18; Unity main-thread GC alloc/event=6574 B (44.92 allocs); ART(Java) alloc/event=8841 B, ART GCs=3; PSS start/peak MB=167/178; db_events=1202, packets_v2=14, batches_v1=1

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 41.2 | 45.5 | 79 |
| track_enqueue | 1.00 | 6.0 | 6.1 | 20 |
| persist_total | 0.15 | 152.3 | 683.7 | 2823 |
| snapshot_batch | 0.15 | 0.7 | 0.8 | 1205 |
| jni_enqueue_batch | 0.15 | 86.3 | 206.7 | 3 |
| uploader_flush | 0.15 | 48.8 | 454.0 | 1649 |
| jni_get_state | 0.01 | 0.8 | 0.8 | 3 |
| jni_read_batch | 0.01 | 3.7 | 3.7 | 840 |
| jni_delete_ack | 0.01 | 3.7 | 4.0 | 0 |
| v7_encode(parse+pack+zstd) | 0.01 | 33.2 | 36.7 | 1365 |
| v7_post_packet | 0.01 | 3.4 | 404.3 | 294 |

Traffic: V7 packets 13 (25321 B), V1 batches 0 (gzip 0 B, json 0 B) -> 21.1 B/event body; persist_calls=186 for 1200 events (avg 6.45 events per call)

## v7_persec

events=90, scenario_ms=92992, process CPU: scenario 234333 µs/event, drain 111 µs/event, total 234444 µs/event; GC0/1/2=9/9/9; Track µs p50/p95/p99=64.1/127.3/165.5; frame ms p99=0.17; Unity main-thread GC alloc/event=28839 B (314.51 allocs); ART(Java) alloc/event=33860 B, ART GCs=1; PSS start/peak MB=160/173; db_events=92, packets_v2=20, batches_v1=1

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 65.5 | 71.8 | 0 |
| track_enqueue | 1.00 | 21.6 | 24.2 | 0 |
| persist_total | 1.21 | 857.8 | 3569.8 | 6690 |
| snapshot_batch | 1.01 | 2.9 | 4.0 | 774 |
| jni_enqueue_batch | 1.00 | 324.0 | 618.8 | 0 |
| uploader_flush | 1.01 | 408.3 | 2801.9 | 6007 |
| jni_get_state | 0.21 | 20.6 | 22.6 | 46 |
| jni_read_batch | 0.22 | 24.9 | 71.3 | 819 |
| jni_delete_ack | 0.21 | 61.6 | 82.4 | 0 |
| v7_encode(parse+pack+zstd) | 0.21 | 66.7 | 82.3 | 2867 |
| v7_post_packet | 0.21 | 133.5 | 2394.2 | 5143 |

Traffic: V7 packets 19 (5641 B), V1 batches 0 (gzip 0 B, json 0 B) -> 62.7 B/event body; persist_calls=109 for 90 events (avg 0.83 events per call)

## v7_single

events=15, scenario_ms=90492, process CPU: scenario 1369333 µs/event, drain 667 µs/event, total 1370000 µs/event; GC0/1/2=6/6/6; Track µs p50/p95/p99=66.8/144.8/144.8; frame ms p99=0.15; Unity main-thread GC alloc/event=114249 B (1290.73 allocs); ART(Java) alloc/event=58982 B, ART GCs=1; PSS start/peak MB=160/172; db_events=17, packets_v2=13, batches_v1=1

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 70.4 | 83.7 | 0 |
| track_enqueue | 1.00 | 25.6 | 37.2 | 0 |
| persist_total | 2.47 | 2064.3 | 7990.7 | 21026 |
| snapshot_batch | 1.60 | 4.7 | 5.1 | 273 |
| jni_enqueue_batch | 1.00 | 288.1 | 589.1 | 0 |
| uploader_flush | 1.60 | 1568.3 | 7169.7 | 20207 |
| jni_get_state | 1.07 | 100.3 | 100.1 | 546 |
| jni_read_batch | 1.07 | 78.5 | 92.7 | 0 |
| jni_delete_ack | 0.80 | 190.9 | 203.8 | 0 |
| v7_encode(parse+pack+zstd) | 0.80 | 132.5 | 132.3 | 3550 |
| v7_post_packet | 0.80 | 451.7 | 5989.4 | 17203 |

Traffic: V7 packets 12 (2091 B), V1 batches 0 (gzip 0 B, json 0 B) -> 139.4 B/event body; persist_calls=37 for 15 events (avg 0.41 events per call)
