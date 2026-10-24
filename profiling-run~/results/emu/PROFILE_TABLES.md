# Profiling tables (emu)

Per event = stage total / events in scenario. Times in µs. cpu = thread CPU, wall = elapsed incl. blocking. Stages nest (inclusive).


## none_burst20f

events=2800, scenario_ms=4664, process CPU: scenario 368 µs/event, drain 0 µs/event, total 368 µs/event; GC0/1/2=0/0/0; Track µs p50/p95/p99=0.0/0.1/0.3; frame ms p99=0.02; Unity main-thread GC alloc/event=282 B (3.32 allocs); ART(Java) alloc/event=12 B, ART GCs=0; PSS start/peak MB=175/176; db_events=0, packets_v2=0, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|

Traffic: V7 packets 0 (0 B), V1 batches 0 (gzip 0 B, json 0 B) -> 0.0 B/event body; persist_calls=None for 2800 events (avg 0.00 events per call)

## none_perframe1

events=1200, scenario_ms=40096, process CPU: scenario 7592 µs/event, drain 0 µs/event, total 7592 µs/event; GC0/1/2=0/0/0; Track µs p50/p95/p99=0.2/0.3/0.4; frame ms p99=0.01; Unity main-thread GC alloc/event=637 B (7.30 allocs); ART(Java) alloc/event=55 B, ART GCs=1; PSS start/peak MB=167/169; db_events=0, packets_v2=0, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|

Traffic: V7 packets 0 (0 B), V1 batches 0 (gzip 0 B, json 0 B) -> 0.0 B/event body; persist_calls=None for 1200 events (avg 0.00 events per call)

## v1_burst100

events=500, scenario_ms=60126, process CPU: scenario 27480 µs/event, drain 40 µs/event, total 27520 µs/event; GC0/1/2=35/35/35; Track µs p50/p95/p99=45.5/136.8/2956.7; frame ms p99=14.46; Unity main-thread GC alloc/event=34903 B (610.93 allocs); ART(Java) alloc/event=41361 B, ART GCs=5; PSS start/peak MB=165/178; db_events=501, packets_v2=0, batches_v1=6

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 68.3 | 132.1 | 0 |
| track_enqueue | 1.00 | 0.7 | 0.7 | 0 |
| persist_total | 0.04 | 468.5 | 1010.0 | 0 |
| snapshot_batch | 0.09 | 0.3 | 0.3 | 0 |
| serialize_json | 0.05 | 26.5 | 36.3 | 0 |
| jni_enqueue_batch | 0.05 | 299.0 | 394.9 | 0 |
| remove_prefix | 0.05 | 0.2 | 0.2 | 0 |
| uploader_flush | 0.04 | 139.4 | 575.1 | 0 |
| jni_get_state | 0.04 | 11.0 | 11.2 | 0 |
| jni_read_batch | 0.03 | 91.0 | 99.3 | 0 |
| jni_delete_ack | 0.01 | 8.6 | 9.0 | 0 |
| v1_parse_queued | 0.03 | 7.9 | 13.8 | 0 |
| v1_send_batch(json+gzip+http) | 0.01 | 15.8 | 436.4 | 0 |
| v1_gzip_body | 0.01 | 9.6 | 10.7 | 0 |
| http_send(wall) | 0.01 | 2.6 | 421.1 | 0 |

Traffic: V7 packets 0 (0 B), V1 batches 5 (gzip 43742 B, json 564347 B) -> 87.5 B/event body; persist_calls=18 for 500 events (avg 27.78 events per call)

## v1_burst20f

events=2800, scenario_ms=4749, process CPU: scenario 1243 µs/event, drain 7 µs/event, total 1250 µs/event; GC0/1/2=51/51/51; Track µs p50/p95/p99=46.1/197.8/4167.3; frame ms p99=13.90; Unity main-thread GC alloc/event=34357 B (613.19 allocs); ART(Java) alloc/event=41209 B, ART GCs=24; PSS start/peak MB=174/189; db_events=2801, packets_v2=0, batches_v1=30

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 111.4 | 159.3 | 0 |
| track_enqueue | 1.00 | 2.5 | 1.9 | 0 |
| persist_total | 0.02 | 570.7 | 1356.1 | 0 |
| snapshot_batch | 0.08 | 0.3 | 0.6 | 0 |
| serialize_json | 0.06 | 25.4 | 31.5 | 0 |
| jni_enqueue_batch | 0.06 | 377.2 | 465.7 | 0 |
| remove_prefix | 0.06 | 0.2 | 0.2 | 0 |
| uploader_flush | 0.02 | 166.0 | 856.2 | 0 |
| jni_get_state | 0.02 | 2.6 | 2.6 | 0 |
| jni_read_batch | 0.02 | 119.4 | 127.5 | 0 |
| jni_delete_ack | 0.01 | 11.7 | 19.4 | 0 |
| v1_parse_queued | 0.02 | 8.0 | 11.1 | 0 |
| v1_send_batch(json+gzip+http) | 0.01 | 19.0 | 690.0 | 0 |
| v1_gzip_body | 0.01 | 10.8 | 13.9 | 0 |
| http_send(wall) | 0.01 | 5.0 | 665.5 | 0 |

Traffic: V7 packets 0 (0 B), V1 batches 29 (gzip 248803 B, json 3206646 B) -> 88.9 B/event body; persist_calls=64 for 2800 events (avg 43.75 events per call)

## v1_perframe1

events=1200, scenario_ms=40092, process CPU: scenario 9717 µs/event, drain 8 µs/event, total 9725 µs/event; GC0/1/2=55/55/55; Track µs p50/p95/p99=95.0/467.4/4707.4; frame ms p99=4.71; Unity main-thread GC alloc/event=37977 B (665.94 allocs); ART(Java) alloc/event=78227 B, ART GCs=28; PSS start/peak MB=169/179; db_events=1201, packets_v2=0, batches_v1=14

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 164.1 | 232.8 | 0 |
| track_enqueue | 1.00 | 59.7 | 62.3 | 0 |
| persist_total | 1.00 | 1495.6 | 2678.0 | 0 |
| snapshot_batch | 2.00 | 4.5 | 5.1 | 0 |
| serialize_json | 1.00 | 83.6 | 105.8 | 0 |
| jni_enqueue_batch | 1.00 | 1014.1 | 1690.8 | 0 |
| remove_prefix | 1.00 | 2.4 | 2.5 | 0 |
| uploader_flush | 1.00 | 305.1 | 774.6 | 0 |
| jni_get_state | 1.00 | 143.1 | 157.1 | 0 |
| jni_read_batch | 0.02 | 110.3 | 114.8 | 0 |
| jni_delete_ack | 0.01 | 8.9 | 9.2 | 0 |
| v1_parse_queued | 0.02 | 9.6 | 13.5 | 0 |
| v1_send_batch(json+gzip+http) | 0.01 | 22.9 | 469.2 | 0 |
| v1_gzip_body | 0.01 | 16.1 | 18.3 | 0 |
| http_send(wall) | 0.01 | 2.8 | 442.6 | 0 |

Traffic: V7 packets 0 (0 B), V1 batches 13 (gzip 113105 B, json 1366486 B) -> 94.3 B/event body; persist_calls=1205 for 1200 events (avg 1.00 events per call)

## v1_persec

events=90, scenario_ms=92991, process CPU: scenario 234111 µs/event, drain 333 µs/event, total 234444 µs/event; GC0/1/2=24/24/24; Track µs p50/p95/p99=96.7/693.6/5964.1; frame ms p99=5.97; Unity main-thread GC alloc/event=58943 B (833.56 allocs); ART(Java) alloc/event=85879 B, ART GCs=2; PSS start/peak MB=162/174; db_events=91, packets_v2=0, batches_v1=20

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 172.4 | 320.3 | 0 |
| track_enqueue | 1.00 | 30.6 | 34.7 | 0 |
| persist_total | 1.22 | 1506.7 | 3771.9 | 0 |
| snapshot_batch | 2.22 | 4.5 | 4.7 | 0 |
| serialize_json | 1.00 | 57.1 | 87.8 | 0 |
| jni_enqueue_batch | 1.00 | 767.5 | 1271.4 | 0 |
| remove_prefix | 1.00 | 2.3 | 2.3 | 0 |
| uploader_flush | 1.22 | 567.3 | 2281.2 | 0 |
| jni_get_state | 1.22 | 156.3 | 175.7 | 0 |
| jni_read_batch | 0.42 | 237.2 | 256.6 | 0 |
| jni_delete_ack | 0.21 | 41.6 | 47.2 | 0 |
| v1_parse_queued | 0.42 | 17.9 | 73.8 | 0 |
| v1_send_batch(json+gzip+http) | 0.21 | 99.1 | 1710.4 | 0 |
| v1_gzip_body | 0.21 | 30.3 | 103.9 | 0 |
| http_send(wall) | 0.21 | 53.4 | 1559.0 | 0 |

Traffic: V7 packets 0 (0 B), V1 batches 19 (gzip 22542 B, json 101408 B) -> 250.5 B/event body; persist_calls=110 for 90 events (avg 0.82 events per call)

## v1_single

events=15, scenario_ms=90474, process CPU: scenario 1405333 µs/event, drain 667 µs/event, total 1406000 µs/event; GC0/1/2=9/9/9; Track µs p50/p95/p99=101.4/212.2/212.2; frame ms p99=0.22; Unity main-thread GC alloc/event=140033 B (1624.07 allocs); ART(Java) alloc/event=115780 B, ART GCs=1; PSS start/peak MB=162/173; db_events=16, packets_v2=0, batches_v1=13

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 124.1 | 159.6 | 0 |
| track_enqueue | 1.00 | 30.3 | 37.5 | 0 |
| persist_total | 2.27 | 2878.1 | 10434.0 | 0 |
| snapshot_batch | 3.27 | 8.1 | 8.7 | 0 |
| serialize_json | 1.00 | 69.7 | 117.2 | 0 |
| jni_enqueue_batch | 1.00 | 943.6 | 2576.9 | 0 |
| remove_prefix | 1.00 | 3.0 | 3.0 | 0 |
| uploader_flush | 2.27 | 1675.4 | 7518.1 | 0 |
| jni_get_state | 2.27 | 499.3 | 752.3 | 0 |
| jni_read_batch | 1.87 | 431.6 | 437.5 | 0 |
| jni_delete_ack | 0.80 | 136.4 | 148.3 | 0 |
| v1_parse_queued | 1.87 | 35.1 | 37.3 | 0 |
| v1_send_batch(json+gzip+http) | 0.80 | 528.3 | 6093.3 | 0 |
| v1_gzip_body | 0.80 | 331.0 | 672.7 | 0 |
| http_send(wall) | 0.80 | 151.6 | 5202.0 | 0 |

Traffic: V7 packets 0 (0 B), V1 batches 12 (gzip 8749 B, json 17758 B) -> 583.3 B/event body; persist_calls=34 for 15 events (avg 0.44 events per call)

## v7_burst100

events=500, scenario_ms=60162, process CPU: scenario 27280 µs/event, drain 20 µs/event, total 27300 µs/event; GC0/1/2=47/47/47; Track µs p50/p95/p99=43.5/193.0/2922.3; frame ms p99=13.25; Unity main-thread GC alloc/event=49528 B (927.62 allocs); ART(Java) alloc/event=40903 B, ART GCs=5; PSS start/peak MB=167/180; db_events=501, packets_v2=6, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 75.4 | 125.5 | 0 |
| track_enqueue | 1.00 | 0.7 | 1.5 | 0 |
| persist_total | 0.04 | 531.8 | 1057.0 | 0 |
| snapshot_batch | 0.08 | 0.3 | 1.0 | 0 |
| serialize_json | 0.05 | 24.9 | 43.6 | 0 |
| jni_enqueue_batch | 0.05 | 303.5 | 407.1 | 0 |
| remove_prefix | 0.05 | 0.3 | 0.3 | 0 |
| uploader_flush | 0.04 | 199.7 | 601.5 | 0 |
| jni_get_state | 0.04 | 8.8 | 9.3 | 0 |
| jni_read_batch | 0.03 | 94.0 | 97.0 | 0 |
| jni_delete_ack | 0.01 | 3.2 | 3.5 | 0 |
| v7_encode(parse+pack+zstd) | 0.01 | 82.2 | 103.7 | 0 |
| v7_post_packet | 0.01 | 3.4 | 377.9 | 0 |

Traffic: V7 packets 5 (9952 B), V1 batches 0 (gzip 0 B, json 0 B) -> 19.9 B/event body; persist_calls=18 for 500 events (avg 27.78 events per call)

## v7_burst20f

events=2800, scenario_ms=4658, process CPU: scenario 1036 µs/event, drain 4 µs/event, total 1039 µs/event; GC0/1/2=75/75/75; Track µs p50/p95/p99=41.4/107.6/4125.2; frame ms p99=6.34; Unity main-thread GC alloc/event=49329 B (933.18 allocs); ART(Java) alloc/event=41203 B, ART GCs=24; PSS start/peak MB=175/188; db_events=2801, packets_v2=29, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 81.7 | 125.0 | 0 |
| track_enqueue | 1.00 | 1.2 | 2.8 | 0 |
| persist_total | 0.04 | 541.3 | 1075.9 | 0 |
| snapshot_batch | 0.12 | 0.3 | 3.9 | 0 |
| serialize_json | 0.09 | 21.6 | 32.3 | 0 |
| jni_enqueue_batch | 0.09 | 317.1 | 406.5 | 0 |
| remove_prefix | 0.09 | 0.2 | 0.2 | 0 |
| uploader_flush | 0.04 | 199.9 | 627.9 | 0 |
| jni_get_state | 0.04 | 4.1 | 4.5 | 0 |
| jni_read_batch | 0.02 | 103.8 | 110.9 | 0 |
| jni_delete_ack | 0.01 | 6.3 | 7.0 | 0 |
| v7_encode(parse+pack+zstd) | 0.01 | 76.0 | 88.2 | 0 |
| v7_post_packet | 0.01 | 4.1 | 411.4 | 0 |

Traffic: V7 packets 28 (56895 B), V1 batches 0 (gzip 0 B, json 0 B) -> 20.3 B/event body; persist_calls=112 for 2800 events (avg 25.00 events per call)

## v7_perframe1

events=1200, scenario_ms=40093, process CPU: scenario 8767 µs/event, drain 8 µs/event, total 8775 µs/event; GC0/1/2=67/67/67; Track µs p50/p95/p99=89.0/188.9/728.9; frame ms p99=0.73; Unity main-thread GC alloc/event=52495 B (981.16 allocs); ART(Java) alloc/event=77660 B, ART GCs=28; PSS start/peak MB=171/182; db_events=1201, packets_v2=14, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 96.6 | 114.3 | 0 |
| track_enqueue | 1.00 | 21.3 | 22.5 | 0 |
| persist_total | 1.01 | 1253.5 | 2394.2 | 0 |
| snapshot_batch | 2.00 | 3.6 | 3.8 | 0 |
| serialize_json | 1.00 | 44.7 | 69.8 | 0 |
| jni_enqueue_batch | 1.00 | 831.1 | 1483.6 | 0 |
| remove_prefix | 1.00 | 2.1 | 2.3 | 0 |
| uploader_flush | 1.01 | 307.3 | 756.8 | 0 |
| jni_get_state | 1.01 | 104.6 | 119.1 | 0 |
| jni_read_batch | 0.02 | 96.8 | 103.6 | 0 |
| jni_delete_ack | 0.01 | 3.6 | 4.9 | 0 |
| v7_encode(parse+pack+zstd) | 0.01 | 89.9 | 111.9 | 0 |
| v7_post_packet | 0.01 | 3.7 | 408.0 | 0 |

Traffic: V7 packets 13 (25878 B), V1 batches 0 (gzip 0 B, json 0 B) -> 21.6 B/event body; persist_calls=1207 for 1200 events (avg 0.99 events per call)

## v7_persec

events=90, scenario_ms=92985, process CPU: scenario 239778 µs/event, drain 111 µs/event, total 239889 µs/event; GC0/1/2=27/27/27; Track µs p50/p95/p99=104.6/4136.9/5100.5; frame ms p99=5.10; Unity main-thread GC alloc/event=73025 B (1192.46 allocs); ART(Java) alloc/event=87472 B, ART GCs=2; PSS start/peak MB=162/172; db_events=91, packets_v2=20, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 185.4 | 476.7 | 0 |
| track_enqueue | 1.00 | 25.6 | 27.7 | 0 |
| persist_total | 1.21 | 1699.5 | 4273.3 | 0 |
| snapshot_batch | 2.21 | 5.5 | 6.5 | 0 |
| serialize_json | 1.00 | 55.7 | 93.8 | 0 |
| jni_enqueue_batch | 1.00 | 862.1 | 1528.1 | 0 |
| remove_prefix | 1.00 | 2.4 | 2.6 | 0 |
| uploader_flush | 1.21 | 680.4 | 2536.2 | 0 |
| jni_get_state | 1.21 | 173.1 | 183.2 | 0 |
| jni_read_batch | 0.42 | 127.0 | 130.8 | 0 |
| jni_delete_ack | 0.21 | 40.9 | 92.5 | 0 |
| v7_encode(parse+pack+zstd) | 0.21 | 145.0 | 323.5 | 0 |
| v7_post_packet | 0.21 | 100.9 | 1708.4 | 0 |

Traffic: V7 packets 19 (5618 B), V1 batches 0 (gzip 0 B, json 0 B) -> 62.4 B/event body; persist_calls=109 for 90 events (avg 0.83 events per call)

## v7_single

events=15, scenario_ms=90351, process CPU: scenario 1469333 µs/event, drain 667 µs/event, total 1470000 µs/event; GC0/1/2=9/9/9; Track µs p50/p95/p99=103.6/161.7/161.7; frame ms p99=0.16; Unity main-thread GC alloc/event=155333 B (2137.87 allocs); ART(Java) alloc/event=133257 B, ART GCs=1; PSS start/peak MB=159/169; db_events=16, packets_v2=13, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 124.0 | 148.6 | 0 |
| track_enqueue | 1.00 | 23.6 | 25.5 | 0 |
| persist_total | 2.27 | 3052.9 | 10178.6 | 0 |
| snapshot_batch | 3.27 | 8.3 | 9.0 | 0 |
| serialize_json | 1.00 | 71.4 | 438.5 | 0 |
| jni_enqueue_batch | 1.00 | 781.4 | 1309.9 | 0 |
| remove_prefix | 1.00 | 2.9 | 3.1 | 0 |
| uploader_flush | 2.27 | 2021.5 | 8214.5 | 0 |
| jni_get_state | 2.27 | 535.6 | 580.9 | 0 |
| jni_read_batch | 1.87 | 259.9 | 287.3 | 0 |
| jni_delete_ack | 0.80 | 135.6 | 153.3 | 0 |
| v7_encode(parse+pack+zstd) | 0.80 | 243.9 | 359.9 | 0 |
| v7_post_packet | 0.80 | 304.2 | 5998.0 | 0 |

Traffic: V7 packets 12 (2091 B), V1 batches 0 (gzip 0 B, json 0 B) -> 139.4 B/event body; persist_calls=34 for 15 events (avg 0.44 events per call)
