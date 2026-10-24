# Profiling tables (emu_smoke)

Per event = stage total / events in scenario. Times in µs. cpu = thread CPU, wall = elapsed incl. blocking. Stages nest (inclusive).


## smoke_v7_perframe

events=600, scenario_ms=20025, process CPU: scenario 8783 µs/event, drain 33 µs/event, total 8817 µs/event; GC0/1/2=54/54/54; Track µs p50/p95/p99=96.7/189.7/5631.7; frame ms p99=5.63; Unity main-thread GC alloc/event=0 B (0.00 allocs); ART(Java) alloc/event=0 B, ART GCs=None; PSS start/peak MB=164/164; db_events=601, packets_v2=8, batches_v1=0

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 117.0 | 216.8 | 0 |
| track_enqueue | 1.00 | 32.4 | 34.6 | 0 |
| persist_total | 1.00 | 1671.8 | 2851.7 | 0 |
| snapshot_batch | 2.00 | 4.1 | 4.6 | 0 |
| serialize_json | 1.00 | 57.5 | 80.2 | 0 |
| jni_enqueue_batch | 1.00 | 1167.9 | 1830.7 | 0 |
| remove_prefix | 1.00 | 2.8 | 2.9 | 0 |
| uploader_flush | 1.00 | 356.7 | 829.0 | 0 |
| jni_get_state | 1.00 | 147.9 | 169.5 | 0 |
| jni_read_batch | 0.02 | 99.9 | 105.3 | 0 |
| jni_delete_ack | 0.01 | 4.2 | 4.4 | 0 |
| v7_encode(parse+pack+zstd) | 0.01 | 85.8 | 145.4 | 0 |
| v7_post_packet | 0.01 | 4.4 | 389.1 | 0 |

Traffic: V7 packets 7 (12642 B), V1 batches 0 (gzip 0 B, json 0 B) -> 21.1 B/event body; persist_calls=602 for 600 events (avg 1.00 events per call)
