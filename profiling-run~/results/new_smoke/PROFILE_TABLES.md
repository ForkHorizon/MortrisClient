# Profiling tables (new_smoke)

Per event = stage total / events in scenario. Times in µs. cpu = thread CPU, wall = elapsed incl. blocking. Stages nest (inclusive).


## v7_perframe1

events=600, scenario_ms=20026, process CPU: scenario 11767 µs/event, drain 33 µs/event, total 11800 µs/event; GC0/1/2=41/41/41; Track µs p50/p95/p99=88.7/233.7/4186.8; frame ms p99=4.19; Unity main-thread GC alloc/event=37041 B (740.50 allocs); ART(Java) alloc/event=9039 B, ART GCs=2; PSS start/peak MB=161/172; db_events=602, packets_v2=11, batches_v1=1

| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |
|---|---|---|---|---|
| track_total | 1.00 | 109.7 | 194.2 | 0 |
| track_enqueue | 1.00 | 7.1 | 7.7 | 0 |
| persist_total | 0.16 | 333.7 | 1171.2 | 0 |
| snapshot_batch | 0.16 | 0.6 | 0.9 | 0 |
| jni_enqueue_batch | 0.15 | 240.7 | 501.4 | 0 |
| uploader_flush | 0.16 | 78.7 | 650.5 | 0 |
| jni_get_state | 0.01 | 0.6 | 0.8 | 0 |
| jni_read_batch | 0.03 | 18.8 | 36.8 | 0 |
| jni_delete_ack | 0.02 | 4.6 | 4.6 | 0 |
| v7_encode(parse+pack+zstd) | 0.02 | 42.6 | 69.3 | 0 |
| v7_post_packet | 0.02 | 5.7 | 532.1 | 0 |

Traffic: V7 packets 10 (13161 B), V1 batches 0 (gzip 0 B, json 0 B) -> 21.9 B/event body; persist_calls=94 for 600 events (avg 6.38 events per call)
