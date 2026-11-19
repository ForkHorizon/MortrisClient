# Phase 2 — current analytics architecture vs Heuriva findings

Read-only audit, 2026-10-24. Client = this repo at `feat/v7-client` (HEAD 3e8ebb8 + c22365b/073df27 audit fixes, unpushed); server = `~/Daliys/Web/MortrisServer-v7` @ `0f5267d`. No code changed, nothing run. File refs are checkable; numbers come from our own reports and are labelled with their protocol.

## 1. Architecture as it is
| Layer | Fact | Where |
|---|---|---|
| Default transport | V1 gzip-JSON batches; V7 opt-in (`UseTransportV7=false`) | `Documentation/V7Transport.md` |
| Event queue | Java SQLite queue via JNI (Android only), sequence number assigned in the insert transaction; identity = (install, epoch, sequence) | `Native~/android/analytics/.../AnalyticsQueue.java`, `Runtime/Internal/AndroidQueueBridge.cs` |
| Batching | `MaximumBatchSize = 100` (constant), timer `UploadInterval = 30 s`; packet limit `MaxRows = 500`, `MaxFrame = 256 KiB`, `MaxRaw = 2 MiB`. No session batching | `AnalyticsUploader.cs:31`, `AnalyticsOptions.cs:18`, `M7FrameEncoder.cs:15` |
| Encoding | Catalog (event shapes) + alias table (per-process context: session, app version, device, locale, tz) + columnar packing; **integer model and string model both ON by default** | `M7Columns.cs`, `V7Session.cs:34` (`IntegerModel = true, StringModel = true`) |
| Compression | zstd 1.5.7 level 1, native, reusable context, pre-digested dictionary | `M7Zstd.cs` |
| Dictionary | Per-project asset, 16,384 B (+ catalog 11,528 B), id = first 8 bytes of SHA-256, fetched once per id and cached on disk; framed in the packet header so the server picks the right one; changing the asset re-fetches automatically | `V7Session.cs:212-252`, `night-run~/work/{dictionary.bin,catalog.json}`, server `docs/v7-transport.md` |
| Frame | "M7", flags, compression mode, catalog id, alias epoch, dictionary id, row count, raw size, body, CRC32 | `M7FrameEncoder.cs` |
| Fallback | Per-batch V1 on unknown shape / protocol error / missing native lib; V7 off after 3 failures | `V7Session.cs`, `V7Transport.md` table |
| Server | Go 1.26 + PostgreSQL; independent decoder `internal/transportv7` (decoder, stream, ids, C#-fixture tests); stream sync `/v2/streams/sync`, aliases, assets, packet endpoints | MortrisServer-v7 |
| Rate limits (hard-coded) | per-install 12/min (burst 30), per-project 30 rps, per-IP 100 rps | server, found in night run |

## 2. Heuriva idea → status in the SDK
| Heuriva finding (`RESEARCH_SUMMARY.md`) | Already in SDK? | Evidence | Gap / what remains |
|---|---|---|---|
| Dictionary of 16/32 KiB is the main lever (−16…−18% at base model) | **Yes, 16 KiB** | `dictionary.bin` = 16,384 B; zstd+dict in `M7Zstd.cs` | 32 KiB not used; our own 16 vs 32 comparison exists in `Theory~/transport-v7/06-experiments` (bench scripts mention both) but was not re-read in this phase |
| `integer`/`string`/`both` models (−23…−28% at batch 300) | **Yes, both models on** | `V7Session.cs:34`, flag bits in `M7FrameEncoder.cs:30` | none functionally; Heuriva says `both` costs +26% encode at batch 300 on a macOS host, our phone data shows V7≈V1 CPU (+7% burst) — the two are different protocols (see §3) |
| Batch 100 → 150…300 | **No** (fixed 100) | `AnalyticsUploader.cs:31` | frame/server limits already allow 500 rows. Heuriva: ≤ a few pp gain, 300+ triggers fallback for part of events |
| Session batching | No | — | Heuriva: within noise; skip |
| Metadata reuse | **Yes (alias table)**, beyond M7 parameter space | `M7Aliases.cs`, `PUT /v2/streams/aliases` | cold-start cost ≈1 KB/install (night-run §2.1) |
| Exact round-trip + independent Go decoder | **Yes** | `Native~/transport-tests` EncoderTests/ExportTests, server `csharp_test.go` | Heuriva's C#→Go path could be a second cross-check |
| Dictionary delivery cost accounting (Heuriva's open gap) | **Partly**: documented, measured | cold start 27.9 KB assets + ≈1 KB alias; V7 not smaller than V1 for sessions < ~500–900 events | no delivery inside the build; not optimized |
| Noise-floor/paired-run CPU method | Different but equivalent: thread CPU + calibration spin + per-run correction (±1–5% on phone) | `night-run~/REPORT.md`, `make_tables.py` | could add an M7-vs-itself control |
| New V8 codec | n/a — Heuriva has none | `PARETO_FRONTIER` | — |

**Net:** the SDK's configuration is, in Heuriva terms, roughly *batch 100 / 16 KiB dict / both / fixed* on top of an alias table and sequence identity. Heuriva's own best-balanced candidate (100/32/base/fixed) is a strictly weaker model set than ours; its payload-max candidates (300/32/both) differ from ours only by dictionary size (32 vs 16 KiB) and batch size (300 vs 100). So almost all of Heuriva's "found" gains were already taken; the remaining open knobs are **dictionary 16→32 KiB** and **batch 100→150/200**.

## 3. Cross-check of numbers (different cohorts/protocols, not mergeable)
- Heuriva `100/32/both/fixed`: 18.27 B/event (3-repeat sweep, 82,923 events, reconstructed bodies); `500/32/both`: 18.09.
- Ours, V7 batch 100, 16 KiB dict: **17.8 B/event** on 974,689 events (REPORT §2.1; dictionary trained on 20% of installs, rest test). Zstd with dict takes columns 24.6 → 18.0.
- Therefore the two pipelines agree to ≈3% on payload at similar settings, which supports that Heuriva's harness measures the same codec. Not a validation of either: cohorts differ (Heuriva 167 installs ≤600 events each vs our 217 installs, all events).
- CPU is not comparable: Heuriva = ratios of host encode time vs M7 default; ours = absolute µs/event on host, emulator and Nothing A142 plus allocations.

## 4. Findings about the current repo (found during the audit)
1. `Documentation/V7Transport.md` "Known gaps" is stale: it says nothing ran on a physical phone and ARMv7 was never executed. Both were done on 2026-10-21/22 (night-run REPORT §8). Needs a doc fix.
2. `night-run~/REPORT.md` opening scope still says "no physical device" while §8 reports one; this is the contradiction that Heuriva's `DATA_INVENTORY` flags. Needs a one-line fix.
3. `MaximumBatchSize = 100` is a constant, not an option; any batch experiment needs a code change (Phase 4 only).
4. Known open defects from the night run, unrelated to Heuriva but relevant to any benchmark: `event_catalog` upsert deadlock under parallel ingest (SQLSTATE 40P01, issue #0126), ≈7 ms/event queue CPU in paced mode (SQLite per event, unprofiled), 77% of encoder allocations are JSON parsing.
5. Existing benchmark infrastructure (reusable in Phase 5): `night-run~/` (28 scripts: host, Unity thread attribution, Android, server load, Firebase TLS sink), `Native~/transport-tests` (unit, e2e, device probe), `Theory~/transport-v7/comparison/` (SDK comparisons + `reproduce.sh`), 1M real-event corpus in `MortrisV7Data/`. Hardware: Mac host, Android emulators, one physical Nothing A142 (arm64 + armeabi-v7a build).

## 5. What this means for Phase 3 (not decisions)
- Candidate A: 32 KiB dictionary (needs: retrain on same corpus, size delta vs +16 KiB cold-start download, break-even sessions; no client change, server import only).
- Candidate B: batch 150/200 (needs a constant → option, delivery-latency/loss model, rate-limit interplay: per-install 12/min).
- Candidate C (ours, not Heuriva's): reduce client CPU/allocs (JSON parse of 77%, queue per-event SQLite cost) — likely bigger real-world win than ±2% bytes.
- Dropped by this audit: session batching, base-only 100/32 candidate, anything recommending models already on.
- Unknown until measured: whether `both` at batch 100 costs +CPU on the phone relative to base (Heuriva's +26% was at batch 300 on host).
