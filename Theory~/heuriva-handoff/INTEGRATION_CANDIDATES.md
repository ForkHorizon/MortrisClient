# Integration candidates (hypotheses, not a plan)

Grades: **Strong** = repeated, paired, exact round trip; **Prelim** = repeated on one host/cohort only; **Hyp** = engineering hypothesis; **None** = no evidence. Nothing is assumed about the current SDK: Phase 2 must check what `Runtime/Internal/Transport` and the server already do (e.g. batch size, dictionary, models) before any item is considered new. All evidence is development-cohort, macOS host, payload bytes.

| # | Opportunity | Research result (source) | Expected benefit | Limits | Compatibility questions | Validation needed | Priority |
|---|---|---|---|---|---|---|---|
| 1 | Dictionary 32 KiB at batch ≈100 (base model) | 100/32/base/fixed: −18.39%, enc 0.997, dec 1.017, 18 rows/6 runs (`mv8__OVERNIGHT` §4). Prelim | Largest saving at ~no encode CPU | Dictionary delivery/update/versioning cost excluded; trained on one project's data | Dictionary id/negotiation on wire; server must hold same dict; V1 fallback; first-session cost | Measure dict download bytes & break-even events per install; Android CPU; real request bytes | High |
| 2 | Larger batch (150–300) | 150/32/base/session −19.79%, enc 1.016; batch ≥300 triggers fallback for some events (`mv8__OVERNIGHT`, sweep json). Prelim | Few % more payload | Latency, loss on crash, queue/SQLite interplay; session batching ≈ noise | Retry/dedup (sequence identity) with larger batches; rate limits | Delivery-latency and loss model; paired device test | Medium |
| 3 | String model (`string`) | 300/32/string/fixed −23.36%, enc 1.123, dec 0.985, 15 rows. Prelim | Extra ~5 pp vs base, cheaper decode | +12% encode; GC impact unknown | Must exist in frame format and server decoder | Allocations/GC and Android CPU; same-workload paired | Medium |
| 4 | `both`/`integer` models | 300/32/both −27.57%, enc +26%, dec +3%. Prelim | Maximum payload | Encode CPU +26–32%; likely costly on low-end phones | Same as 3 | Device CPU/battery before any decision | Low until device data |
| 5 | Noise-floor method for CPU comparisons | Paired adjacent runs, randomized order, M7-vs-itself 0.998 (`mv8__OVERNIGHT` §4). Strong (method) | Defines what ≈1–2% differences mean | Within-session only | None | Reuse in our own load-corrected harness | Info |
| 6 | Independent Go decoder + exact round-trip gate | 0 failed rows, all frames decoded by Go (`mv8__FINAL_SESSION_REPORT`). Strong | Regression safety for any encoder change | Supported-field subset only | Our server already has its own decoder (Phase 2 to compare) | Cross-check Heuriva C#→Go path against our fixtures | Medium |
| 7 | Replay harness (`research/telemetry-v7`) | stdin-JSON → frames via C# + native zstd (`implementations/`). Source only | Fast offline parameter sweeps | Needs M7 sources, zstd, .NET 10 | Harness references a frozen snapshot; may be stale vs our `feat/v7-client` | Re-point at current client sources | Low |
| 8 | Batching "session" mode | Differences within noise (`mv8__FOUR_HOUR` §6). Prelim | None proven | — | — | Skip unless device data suggest otherwise | Low |
| 9 | New V8 codec family | No evidence; Heuriva states none tested (`mv8__PARETO_FRONTIER`). None | — | — | — | Needs contract (`mv8__RESEARCH_CONTRACT`), sealed cohort | Out of scope |
| 10 | Confirmation cohort / device benchmarks | Heuriva's top-priority gap. Unavailable | Turns exploratory into publishable | Raw data privacy | Our night-run data (994k events, A142 phone) may partly cover device side | Plan in Phase 5 | Plan later |

## Reading rule
A byte saving that needs extra dictionary distribution, CPU or latency is not yet an end-to-end improvement. Rows 1–4 must be re-measured in the real SDK (Phase 4/5) before any claim.
