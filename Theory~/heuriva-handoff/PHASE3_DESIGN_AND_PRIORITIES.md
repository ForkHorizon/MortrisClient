# Phase 3 — improvement design and prioritization

2026-10-24. Design only: no code changed, no new benchmark run. Evidence = our own local data (`night-run~/`, `Theory~/transport-v7/06-experiments/results/`, `MortrisV7Data` corpus) plus the imported Heuriva data (`data/candidate_summary.csv`). Every estimate is labelled; "est." = arithmetic on existing numbers, not a measurement of the product.

## 1. The new fact that reorders the list
In the real corpus (`night-run~/work/puzzle-1m.jsonl.gz`, 997,076 events, 34,837 V1 batches, 239 installs) batches grouped by (install, `sent_at_client`) are **28.6 events on average (median 27, p90 47)**. Only **8.9% of events travel in batches of 100**; 90.8% travel in batches under 60.

Our headline "17.8 B/event" is for batch 100. Our own table (REPORT §2.1) gives 24.6 at batch 30 and 41.9 at batch 10. Interpolating (log–log, est.) over the real distribution: **≈24.9 B/event at current flush behaviour**, not 17.8. Caveats: these batches were produced by the V1 SDK's flush policy; V7 reads up to 100 queued rows per upload tick (`AnalyticsUploader.cs:31`), so it should behave the same, but this was not verified on a V7 stream.

Consequences: Heuriva's "batch 150–300" idea is irrelevant until packets actually fill up, and the dominant byte lever is **how many events each packet carries**.

## 2. Candidates
Benefit = payload bytes/event unless stated. C = complexity (S/M/L), R = compatibility/regression risk.

| ID | Candidate | Evidence | Est. benefit | C | R | Decision |
|---|---|---|---|---|---|---|
| A | **Fuller packets**: coalesce uploads (longer interval, or send only when ≥N rows queued / age ≥ T, cap 100 rows; later cap up to the 500 the frame allows) | Own batch-size curve + real batch distribution; Heuriva curve agrees in direction (batch 50 no-dict worse, `data/candidate_summary.csv`) | 24.9 → 20.4 (x2 merge, −18%) → 18.8 (x3, −24%) → 18.3 (x4) B/event. Est., needs packet-size distribution measured on V7 | S | Low for correctness (SQLite queue is durable, V1 path unchanged). Cost is **delivery latency** and fewer, larger uploads; per-install rate limit 12/min is not a problem | **SHORTLIST #1.** Needs your decision on acceptable delay |
| B | **Embed catalog+dictionary in the build** (cache seed) instead of downloading at first run | Cold start 27.9 KB assets + ≈1 KB alias/install (REPORT §2.1). Median install in corpus has 1,505 events (≈38 KB of packets) | Fleet bytes (est.): 31.8 MB → 25.1 MB, assets are **21.8%** of all V7 bytes in this corpus; median install 66.5 KB → 38.5 KB. Also removes 2 requests and the "<500–900 events V7 not smaller than V1" gap | M | Medium: asset ids must match the server's current ids, else normal re-fetch (already supported, `V7Session.cs:216`); build step must stay in sync with imports | **SHORTLIST #2** |
| C | **Streaming JSON → M7Event parse** (drop `Dictionary<string,object>` tree in `MiniJson`) | Host stage table: JSON parse 3.3 of 7.6 µs/event, 16.6 of 21.6 KB allocs/event (REPORT §2.2). Phone: V7 +7% CPU, +42% GCs vs V1 | est. host −40% encode CPU, −75% allocations; phone effect unmeasured | M | Medium-low: guarded by existing fixtures, Python reference and Go decoder tests | **SHORTLIST #3** |
| D | **Queue CPU in paced mode** (≈7 ms/event vs 0.9 ms burst; hypothesis: one SQLite transaction per event) | Phone paced runs, REPORT §8; never profiled | unknown; could dwarf C (7 ms vs ~0.9 ms/event) | S–M | Medium: touches durability semantics (journal/sequence in same transaction) | **Investigate first** (small profiling task, then decide) |
| E | Dictionary 16 → 32 KiB | Our `bench-real.json`: dict16 19.45 vs dict32 19.11 B/event (−1.7%); Heuriva base-model 20.01 → 19.49 (−2.6%) | ≈0.3–0.5 B/event for +16 KiB download per install → pays back after ≈32–50k events/install; median install 1.5k, p90 11k | S | Low | **Drop** (negative net for typical installs) |
| F | Batch cap >100 (150–300) | Heuriva payload gain; real batches 8.9% ≥100 | ~0 until A exists; then ≤ few % | S | Server row limit not confirmed (client `MaxRows=500`) | **Defer**, fold into A's second step |
| G | Models (`integer`/`string`/`both`), base-only candidate, session batching | Already on (`V7Session.cs:34`) / within noise (Heuriva) | 0 | – | – | **Drop** |
| H | Fixed-point float mode (not ported; floats are raw IEEE per docs) | Not quantified in our ablation | unknown | M | Format change, needs server decoder | **Defer**, quantify first |
| I | New V8 codec | Heuriva: none exists | – | L | – | **Out of scope** |
| J | Server `event_catalog` upsert deadlock (#0126), stale docs ("Known gaps", REPORT scope line) | Night run | reliability / correctness of docs, not bytes | S | Low | **Housekeeping**, independent of Heuriva work |

## 3. Interaction notes
- A and B multiply: A cuts steady-state bytes (−18…−24%), B cuts the per-install fixed cost (−21% of fleet bytes). Combined est. fleet total ≈ 25.1 MB × (0.76…0.82) + ... not simply additive; remeasure after implementing.
- A trades **latency for bytes**; if analytics events need near-real-time delivery for some event types, A needs a bypass (e.g. flush now on app pause/quit — the existing flush paths must be preserved).
- C and D are CPU/GC levers; A makes C slightly better (fewer, larger encodes).
- E is dropped on a total-cost basis; if assets get embedded (B) the download argument weakens, but 16 KiB inside the build is still +16 KiB APK size for ≈2%.

## 4. Proposed shortlist (for approval)
1. **A** fuller packets — S, highest est. gain, needs latency policy decision.
2. **B** embedded assets — M, removes ~22% of V7 bytes in this corpus.
3. **C** streaming parse — M, CPU/GC, guarded by existing tests.
4. **D** profiling of the queue — a small measurement task before any design (can run in Phase 5 style, needs the phone).
Housekeeping J rides along. Drop E, G; defer F, H; I out of scope.

## 5. Open decisions for you
1. Acceptable extra delivery delay for A (e.g. 30 s → 60/90 s, or "send at ≥50 rows or ≥90 s, always on pause/quit"). Which event types, if any, must stay immediate?
2. Is shipping the dictionary/catalog inside the build acceptable (needs a build-time step and updates when the project's assets change)?
3. Do I fix the stale docs and the REPORT scope line now (J)?

## 6. Evidence limits
Corpus covers 239 installs, not full lifetimes (per-install event totals are lower bounds); the log–log batch interpolation uses three measured points; V1 batches in the corpus reflect the V1 SDK's flush timer, not V7's. Fleet-bytes figures use 29 KB cold start per install and exclude HTTP headers/TLS. Nothing above is a product measurement; Phase 4/5 must verify each item on the real SDK.
