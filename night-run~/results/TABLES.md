
### Android SDKs: API 35 emulator (arm64, 6000 events/run, 3 runs; Firebase = production-mode rerun)

| mode | runs | app CPU us/ev (corrected) | net of harness baseline | GMS process net us/ev | net alloc B/ev | PSS growth MB | java peak MB | native peak MB | track p50 us | track p99 us | wire body B/ev | wire +hdr B/ev | delivered % | CPU spread % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| amplitude_b100 | 3 | 1,593 | 1,443 | -1 | 68,216 | 40.4 | 51.1 | 19.3 | 39 | 133 | 1,995.6 | 1,998.2 | 16.7 | 26 |
| amplitude_default | 3 | 2,608 | 2,458 | 10 | 68,171 | 44.3 | 51.2 | 19.4 | 43 | 272 | 2,010.1 | 2,015.5 | 17.2 | 2 |
| base_map | 3 | 150 | 0 | 0 | 0 | 6.5 | 21.2 | 16.0 | 1 | 4 | n/a | n/a | 0.0 | 32 |
| ga_default | 3 | 598 | 448 | 1 | 37,489 | 65.8 | 36.8 | 57.7 | 1 | 5 | 75.5 | 77.7 | 58.8 | 19 |
| hyperkit_core | 3 | 152 | 2 | 1,554 | 2,858 | 9.0 | 21.2 | 16.0 | 1 | 5 | 383.7 | 383.8 | 100.0 | 50 |
| hyperkit_ctx | 3 | 178 | 28 | 7 | 11,271 | 39.1 | 25.6 | 16.0 | 7 | 22 | 1,148.1 | 1,148.2 | 100.0 | 22 |
| firebase | 3 | 1,889 | 1,739 | 10,273 | 205,958 | 20.2 | 33.3 | 26.2 | 1 | 16 | n/a | n/a | 0.0 | 100 |

### Android SDKs: API 25 emulator (arm64, 3000 events/run, 3 runs; sinks for Firebase/Adjust/Facebook)

| mode | runs | app CPU us/ev (corrected) | net of harness baseline | GMS process net us/ev | net alloc B/ev | PSS growth MB | java peak MB | native peak MB | track p50 us | track p99 us | wire body B/ev | wire +hdr B/ev | delivered % | CPU spread % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| adjust | 3 | 37,642 | 37,495 | 283 | 5,005,774 | 35.4 | 32.2 | 18.0 | 5 | 151 | n/a | n/a | 0.0 | 23 |
| amplitude_default | 3 | 2,295 | 2,148 | 8 | 101,888 | 23.9 | 18.0 | 19.4 | 7 | 22 | 2,005.5 | 2,010.8 | 34.3 | 10 |
| base_map | 3 | 148 | 0 | 0 | 0 | 7.6 | 10.8 | 16.8 | 1 | 12 | n/a | n/a | 0.0 | 54 |
| facebook | 3 | 651 | 504 | 2 | 75,566 | 22.4 | 16.1 | 18.6 | 31 | 163 | n/a | n/a | 0.0 | 6 |
| firebase | 3 | 1,088 | 940 | 1,538 | 47,908 | 15.8 | 17.0 | 17.9 | 5 | 59 | n/a | n/a | 0.0 | 23 |
| ga_default | 3 | 1,163 | 1,016 | 4 | 96,223 | 33.2 | 17.3 | 28.0 | 2 | 19 | 75.6 | 76.8 | 104.8 | 8 |
| hyperkit_core | 3 | 225 | 78 | 2 | 3,311 | 14.5 | 14.8 | 17.2 | 2 | 12 | 383.3 | 383.5 | 100.0 | 9 |
| hyperkit_ctx | 3 | 243 | 95 | 2 | 13,420 | 26.5 | 12.6 | 17.2 | 8 | 45 | 1,132.1 | 1,132.3 | 100.0 | 9 |

### Paced replay, 2 events/s, 600 events (one run; includes idle timers)

| mode | app CPU us/ev | GMS us/ev | alloc B/ev | PSS growth MB | wire B/ev | delivered % | init CPU ms |
|---|---|---|---|---|---|---|---|
| amplitude_default | 20,044 | 530 | 103,174 | 6.9 | 1,960.7 | 100.0 | 2 |
| base_map | 13,817 | 958 | 12,955 | 12.9 | n/a | 0.0 | 0 |
| firebase | 9,275 | 10,574 | 285,098 | 10.8 | n/a | 0.0 | 0 |
| ga_default | 29,398 | 548 | 72,393 | 15.2 | 133.3 | 102.2 | 49 |
| hyperkit_core | 6,981 | 123 | 17,008 | 8.3 | 382.2 | 100.2 | 25 |
| hyperkit_ctx | 8,259 | 241 | 25,937 | 6.8 | 1,115.5 | 100.2 | 6 |

### Unity IL2CPP probe (API 35 emulator)

| cell | runs | net CPU us/ev (vs empty player) | Track p50 us | Track p99 us | frame p99 ms | GC runs | mono growth KB | PSS growth MB | V7 packets | V1 batches |
|---|---|---|---|---|---|---|---|---|---|---|
| burst/none | 3 | n/a | 0.0 | 0 | 0.0 | 1 | 36 | 0.8 | 0 | 0 |
| burst/v1 | 3 | 428 | 11.5 | 772 | 5.6 | 55 | 2,212 | 15.3 | 0 | 30 |
| burst/v7 | 3 | 402 | 11.8 | 719 | 6.3 | 78 | 3,860 | 13.4 | 30 | 0 |
| paced/none | 3 | n/a | 0.0 | 0 | 0.0 | 0 | 152 | 0.7 | 0 | 0 |
| paced/v1 | 3 | 1,099 | 40.6 | 798 | 0.8 | 58 | 1,092 | 8.5 | 0 | 13 |
| paced/v7 | 3 | 3,719 | 42.7 | 803 | 0.8 | 73 | 4,456 | 9.2 | 13 | 0 |

### Data fidelity (1500 real events, marker property)

| mode | delivered % | events fully preserved % | properties lost % | lost kinds | strings truncated | type changed |
|---|---|---|---|---|---|---|
| ga_default | 100.0 | 95.0 | 0.22 | {'bool': 73, 'str_empty': 2} | 0 | 0 |
| amplitude_default | 84.7 | 100.0 | 0.00 | {} | 0 | 0 |
| hyperkit_ctx | 100.0 | 100.0 | 0.00 | {} | 0 | 0 |

### Firebase Analytics 23.0.0, real uploads captured (API 25, TLS sink)

| run | uploads | events | gzip body B/ev | raw proto B/ev | events/upload |
|---|---|---|---|---|---|
| debug_r1 | 984 | 3003 | 368.4 | 897 | 3 |
| debug_r2 | 1924 | 3003 | 583.1 | 1,033 | 2 |
| debug_r3 | 1976 | 3003 | 602.6 | 1,040 | 2 |
| prod_r1 | 35 | 3003 | 73.2 | 741 | 86 |
| prod_r2 | 35 | 3003 | 73.1 | 742 | 86 |
| prod_r3 | 35 | 3003 | 73.1 | 742 | 86 |

### Host (macOS arm64, .NET 10) - V7 encoder vs V1 gzip, all 974,689 real events, median of 5 runs

| metric | V7 | V1 (gzip fast) |
|---|---|---|
| wire bytes / event | 17.82 | 158.0 |
| CPU ns / event (thread CPU) | 7,744 | 985 |
| CPU ns / event load-corrected | 7,416 | - |
| alloc bytes / event | 21,616 | 1,471 |
| of which JSON parse (CPU ns / alloc B) | 3,555 / 16,561 | - |
| p50 / p95 / p99 CPU ns per event (per 100-event batch) | 6,758 / 11,980 / 18,046 | - |
| GC gen0 / gen2 collections | 3,512 / 123 | - |

### Server decode (Go, GOMAXPROCS=1, holdout 763,661 events)

| path | CPU ns/event | alloc B/event | p99 ns | RSS MB |
|---|---|---|---|---|
| V7 packet decode | 6,706 | 7,841 | 11,650 | 41 |
| V1 gunzip + DecodeBatchIngestRequest | 18,548 | n/a | 23,990 | 170 |

### Server end-to-end ingest (Go server + PostgreSQL, ~41k real events, rate-limited to 25 req/s)

| mode | concurrency | runs | server CPU us/ev | PostgreSQL CPU us/ev | server RSS MB | PG RSS MB | errors | events stored |
|---|---|---|---|---|---|---|---|---|
| v1 | seq | 3 | 143 | 90 | 149 | 230 | 0 | 40,772 |
| v1 | par6 | 3 | 136 | 90 | 148 | 280 | 0 | 40,772 |
| v7 | seq | 3 | 126 | 92 | 150 | 231 | 0 | 40,772 |
| v7 | par6 | 3 | 118 | 90 | 149 | 282 | 0 | 40,772 |