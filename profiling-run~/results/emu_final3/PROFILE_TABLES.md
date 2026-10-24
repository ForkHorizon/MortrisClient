# Profiling tables (emu_final3)

Per event = stage total / events in scenario. Times in µs. cpu = thread CPU, wall = elapsed incl. blocking. Stages nest (inclusive).


## v1_perframe1

events=1200, scenario_ms=39995, process CPU: scenario 12400 µs/event, drain 17 µs/event, total 12417 µs/event; GC0/1/2=19/19/19; Track µs p50/p95/p99=49.9/101.0/217.6; frame ms p99=0.22; Unity main-thread GC alloc/event=15865 B (64.75 allocs); ART(Java) alloc/event=9540 B, ART GCs=4; PSS start/peak MB=164/174; db_events=1202, packets_v2=0, batches_v1=15

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 52.8 | 56.6 | 75 |
| track_enqueue | 1.00 | 7.3 | 7.9 | 7 |
| persist_total | 0.16 | 214.8 | 948.0 | 4601 |
| snapshot_batch | 0.15 | 0.6 | 0.7 | 1195 |
| jni_enqueue_batch | 0.15 | 125.2 | 333.8 | 0 |
| uploader_flush | 0.15 | 74.7 | 595.0 | 3441 |
| jni_get_state | 0.01 | 0.8 | 0.8 | 0 |
| jni_read_batch | 0.01 | 6.5 | 11.5 | 700 |
| jni_delete_ack | 0.01 | 12.1 | 15.5 | 0 |
| v1_parse_queued | 0.01 | 26.3 | 47.5 | 4086 |
| v1_send_batch(json+gzip+http) | 0.01 | 18.9 | 508.8 | 2031 |
| v1_gzip_body | 0.01 | 11.3 | 11.8 | 737 |
| http_send(wall) | 0.01 | 2.4 | 483.6 | 481 |

Traffic: V7 packets 0 (0 B), V1 batches 13 (gzip 112758 B, json 1364084 B) -> 94.0 B/event body; persist_calls=187 for 1200 events (avg 6.42 events per call)

## v7_burst100

events=500, scenario_ms=60163, process CPU: scenario 26220 µs/event, drain 40 µs/event, total 26260 µs/event; GC0/1/2=7/7/7; Track µs p50/p95/p99=13.7/18.9/45.0; frame ms p99=1.53; Unity main-thread GC alloc/event=7671 B (51.05 allocs); ART(Java) alloc/event=6185 B, ART GCs=1; PSS start/peak MB=162/175; db_events=502, packets_v2=7, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 14.8 | 14.9 | 483 |
| track_enqueue | 1.00 | 0.6 | 0.7 | 483 |
| persist_total | 0.04 | 118.8 | 568.9 | 1614 |
| snapshot_batch | 0.03 | 0.1 | 0.1 | 803 |
| jni_enqueue_batch | 0.01 | 61.4 | 76.7 | 0 |
| uploader_flush | 0.03 | 53.5 | 486.9 | 1024 |
| jni_get_state | 0.02 | 2.9 | 3.3 | 0 |
| jni_read_batch | 0.02 | 4.2 | 4.2 | 811 |
| jni_delete_ack | 0.01 | 6.1 | 9.1 | 0 |
| v7_encode(parse+pack+zstd) | 0.01 | 29.0 | 31.2 | 1516 |
| v7_post_packet | 0.01 | 4.1 | 431.0 | 164 |

Traffic: V7 packets 5 (9692 B), V1 batches 0 (gzip 0 B, json 0 B) -> 19.4 B/event body; persist_calls=19 for 500 events (avg 26.32 events per call)

## v7_burst20f

events=2800, scenario_ms=4664, process CPU: scenario 646 µs/event, drain 14 µs/event, total 661 µs/event; GC0/1/2=9/9/9; Track µs p50/p95/p99=14.8/38.5/74.3; frame ms p99=0.58; Unity main-thread GC alloc/event=5959 B (36.76 allocs); ART(Java) alloc/event=5701 B, ART GCs=4; PSS start/peak MB=172/186; db_events=2802, packets_v2=30, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 16.3 | 17.4 | 573 |
| track_enqueue | 1.00 | 0.8 | 1.2 | 192 |
| persist_total | 0.01 | 116.5 | 522.5 | 2406 |
| snapshot_batch | 0.01 | 0.1 | 0.1 | 806 |
| jni_enqueue_batch | 0.01 | 74.0 | 98.1 | 4 |
| uploader_flush | 0.01 | 41.6 | 423.4 | 2329 |
| jni_get_state | 0.01 | 0.5 | 0.6 | 0 |
| jni_read_batch | 0.01 | 3.2 | 3.4 | 841 |
| jni_delete_ack | 0.01 | 4.5 | 7.7 | 0 |
| v7_encode(parse+pack+zstd) | 0.01 | 27.5 | 30.0 | 2247 |
| v7_post_packet | 0.01 | 3.6 | 379.3 | 247 |

Traffic: V7 packets 28 (56320 B), V1 batches 0 (gzip 0 B, json 0 B) -> 20.1 B/event body; persist_calls=22 for 2800 events (avg 127.27 events per call)

## v7_perframe1

events=1200, scenario_ms=39995, process CPU: scenario 7283 µs/event, drain 0 µs/event, total 7283 µs/event; GC0/1/2=8/8/8; Track µs p50/p95/p99=46.4/77.0/136.6; frame ms p99=0.14; Unity main-thread GC alloc/event=6569 B (44.89 allocs); ART(Java) alloc/event=8854 B, ART GCs=3; PSS start/peak MB=165/177; db_events=1202, packets_v2=15, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 48.4 | 51.0 | 96 |
| track_enqueue | 1.00 | 9.0 | 9.5 | 31 |
| persist_total | 0.16 | 154.5 | 721.9 | 2697 |
| snapshot_batch | 0.15 | 0.6 | 0.7 | 1215 |
| jni_enqueue_batch | 0.15 | 84.6 | 206.7 | 20 |
| uploader_flush | 0.15 | 54.6 | 498.0 | 1481 |
| jni_get_state | 0.01 | 0.8 | 0.8 | 0 |
| jni_read_batch | 0.01 | 5.4 | 8.4 | 696 |
| jni_delete_ack | 0.01 | 4.2 | 7.2 | 0 |
| v7_encode(parse+pack+zstd) | 0.01 | 36.5 | 49.5 | 2239 |
| v7_post_packet | 0.01 | 4.0 | 428.3 | 270 |

Traffic: V7 packets 13 (24954 B), V1 batches 0 (gzip 0 B, json 0 B) -> 20.8 B/event body; persist_calls=187 for 1200 events (avg 6.42 events per call)

## v7_persec

events=90, scenario_ms=92989, process CPU: scenario 216667 µs/event, drain 111 µs/event, total 216778 µs/event; GC0/1/2=8/8/8; Track µs p50/p95/p99=62.3/90.9/157.0; frame ms p99=0.16; Unity main-thread GC alloc/event=28621 B (312.48 allocs); ART(Java) alloc/event=34224 B, ART GCs=1; PSS start/peak MB=159/171; db_events=92, packets_v2=21, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 60.4 | 64.9 | 0 |
| track_enqueue | 1.00 | 20.9 | 22.0 | 0 |
| persist_total | 1.23 | 678.5 | 2641.4 | 8283 |
| snapshot_batch | 1.01 | 2.8 | 4.3 | 728 |
| jni_enqueue_batch | 1.00 | 275.3 | 642.6 | 0 |
| uploader_flush | 1.01 | 302.9 | 1876.9 | 7464 |
| jni_get_state | 0.21 | 17.0 | 16.8 | 46 |
| jni_read_batch | 0.22 | 14.5 | 14.5 | 910 |
| jni_delete_ack | 0.21 | 50.8 | 56.9 | 0 |
| v7_encode(parse+pack+zstd) | 0.21 | 62.1 | 165.4 | 2731 |
| v7_post_packet | 0.21 | 90.7 | 1525.8 | 4870 |

Traffic: V7 packets 19 (5637 B), V1 batches 0 (gzip 0 B, json 0 B) -> 62.6 B/event body; persist_calls=111 for 90 events (avg 0.81 events per call)
