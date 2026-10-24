# Profiling tables (emu_final2)

Per event = stage total / events in scenario. Times in µs. cpu = thread CPU, wall = elapsed incl. blocking. Stages nest (inclusive).


## v7_burst20f

events=2800, scenario_ms=4663, process CPU: scenario 493 µs/event, drain 161 µs/event, total 654 µs/event; GC0/1/2=12/12/12; Track µs p50/p95/p99=14.9/42.6/98.9; frame ms p99=2.76; Unity main-thread GC alloc/event=7425 B (49.20 allocs); ART(Java) alloc/event=5711 B, ART GCs=4; PSS start/peak MB=174/189; db_events=2802, packets_v2=30, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 17.6 | 21.6 | 635 |
| track_enqueue | 1.00 | 0.9 | 1.4 | 97 |
| persist_total | 0.01 | 130.4 | 592.2 | 2954 |
| snapshot_batch | 0.01 | 0.1 | 0.1 | 805 |
| jni_enqueue_batch | 0.01 | 65.7 | 88.7 | 401 |
| uploader_flush | 0.01 | 63.9 | 501.1 | 2358 |
| jni_get_state | 0.01 | 0.5 | 0.5 | 1 |
| jni_read_batch | 0.01 | 17.8 | 18.8 | 1458 |
| jni_delete_ack | 0.01 | 4.6 | 8.9 | 1 |
| v7_encode(parse+pack+zstd) | 0.01 | 32.7 | 40.2 | 2095 |
| v7_post_packet | 0.01 | 5.4 | 429.6 | 295 |

Traffic: V7 packets 28 (56417 B), V1 batches 0 (gzip 0 B, json 0 B) -> 20.1 B/event body; persist_calls=25 for 2800 events (avg 112.00 events per call)

## v7_persec

events=90, scenario_ms=92958, process CPU: scenario 227556 µs/event, drain 111 µs/event, total 227667 µs/event; GC0/1/2=39/39/39; Track µs p50/p95/p99=66.0/89.7/199.0; frame ms p99=0.20; Unity main-thread GC alloc/event=111087 B (1023.70 allocs); ART(Java) alloc/event=34953 B, ART GCs=1; PSS start/peak MB=160/173; db_events=92, packets_v2=21, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 64.2 | 69.5 | 0 |
| track_enqueue | 1.00 | 21.0 | 21.4 | 0 |
| persist_total | 1.21 | 1814.2 | 4883.8 | 30993 |
| snapshot_batch | 1.03 | 3.5 | 3.6 | 592 |
| jni_enqueue_batch | 1.00 | 1194.3 | 2211.2 | 34588 |
| uploader_flush | 1.03 | 514.8 | 2559.8 | 4369 |
| jni_get_state | 0.21 | 13.3 | 13.8 | 46 |
| jni_read_batch | 0.22 | 202.8 | 347.5 | 8920 |
| jni_delete_ack | 0.21 | 54.7 | 86.7 | 46 |
| v7_encode(parse+pack+zstd) | 0.21 | 66.5 | 169.2 | 3322 |
| v7_post_packet | 0.21 | 115.6 | 1876.1 | 3277 |

Traffic: V7 packets 19 (5641 B), V1 batches 0 (gzip 0 B, json 0 B) -> 62.7 B/event body; persist_calls=109 for 90 events (avg 0.83 events per call)
