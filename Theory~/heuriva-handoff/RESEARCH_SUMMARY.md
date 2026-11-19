# Heuriva research summary for the MORTRIS analytics SDK

Sources are file names in `reports/` (prefix omitted: `mv8` = `research__mortris-v8__`, `av2` = `docs__architecture-v2__`). All numbers: development cohort, one macOS arm64 host, **payload bytes/event** unless said otherwise.

## 1. What M7 is
Columnar, alias-table/catalog-based event frame compressed with zstd + project dictionary (the same V7 transport this repo's client/server implement; see `Theory~/transport-v7/`). Heuriva treats the frozen C# encoder (`Daliys.Analytics.Internal.Transport`, files `M7Aliases/Catalog/Columns/Event/EventEncoder/FrameEncoder/Zstd`, `MiniJson`) plus an independent Go decoder as the reference (`mv8__BASELINE_REPORT`, `implementations/research__telemetry-v7__*`, `src__fhel__problems__telemetry_v7.py`).

## 2. What Heuriva tested
Not a new codec. An autonomous lab ("Luna" model directing Architecture V2) swept the finite M7 parameter domain: 7 batch sizes × 3 dictionary sizes (0/16/32 KiB) × 4 models (base/string/integer/both) × 2 batching (fixed/session) = **168 configs** (`mv8__FOUR_HOUR_LIVE_RESEARCH_REPORT` §1, `mv8__OVERNIGHT_RESEARCH_RECONCILIATION` §2). Union coverage 168/168 but 63 configs have a single explore observation (coverage ≠ paired measurement). 4 overnight attempts (412 model calls) all stopped early; no 8-hour campaign completed (`mv8__OVERNIGHT…` header, `av2__ARCHITECTURE_RECOVERY_REPORT`).

## 3. Frozen baseline and data identity
M7 default = batch 100, dict 0 KiB, model base, fixed: **23.883 B/event**. Dataset `puzzle-1m` sha256 `8475bd3d37b007576371548518793e0ffa7c85821557c1a967b309e54a656ca3`; 167 development installations, 82,923 events (first 600 per install) in the sweep (`benchmarks/trusted_m7_full_dev_20261021.json`). Evaluator v6 / code sha in `manifests/heuriva_data_manifest_20261021.json`, HEAD `1535b9f1…`.

## 4–5. Best candidates (paired, M7-relative; `mv8__OVERNIGHT…` §4)
| Config batch/dict/model/batching | B/event | vs M7 | Encode CPU | Decode CPU | rows (runs) | Note |
|---|---|---|---|---|---|---|
| 300/32/both/fixed | 17.30 | −27.57% | 1.265 | 1.031 | 3 (1) (13 in 4h store: 1.274±0.012) | max payload saving |
| 500/32/both/session | 17.91 | −25.02% | 1.321 | 1.017 | 8 (4) | |
| 300/32/string/fixed | 18.31 | −23.36% | 1.123 | 0.985 | 15 (6) | decode below ref |
| 150/32/base/session | 19.16 | −19.79% | 1.016 | 1.012 | 15 (6) | |
| **100/32/base/fixed** | 19.49 | −18.39% | 0.997 | 1.017 | 18 (6) | best balanced |
| 100/16/base/fixed | 20.01 | −16.21% | 0.997 | 1.019 | 15 (6) | |
| 100/0/base/fixed (M7 vs itself) | 23.88 | 0 | 0.998 | 0.998 | 5 | noise floor ≈1–2% |
Single-run explore points reached −29.66% (300/32/both/fixed, geometric ratio metric, different from pooled −27.57%): screening only. Eliminated: batch 25–50 without dictionary (+11…+16% bytes). Of 55 configs with ≥3 rows, 32 are Pareto non-dominated (bytes, enc, dec) — a wide frontier means a trade-off, not many good options.

## 6. CPU/memory evidence
Encode ratio is host-CPU only (macOS, ratio candidate/M7). Payload-first candidates cost +12…+32% encode. **No allocation/GC, no Android CPU, no peak memory** in the Heuriva sweeps (`mv8__OVERNIGHT…` §6). Such numbers exist only in our own `night-run~/REPORT.md` for V7 vs V1 (host 7.7 µs/event, 21.6 KiB/event allocs, phone/emulator parity), measured under a different protocol (`mv8__PARETO_FRONTIER`, `mv8__BASELINE_REPORT`).

## 7. Dictionary and batching
Dictionary 16/32 KiB gives most of the saving; **delivery/update cost is not included** in any saving. Batch ≥300 triggered M7 fallback for 300–1500 events/config in the full sweep. `session` vs `fixed` batching: differences within noise for most pairs. Batch 300–500 + 32 KiB dict captures most of the payload gain (`mv8__FOUR_HOUR…` §7).

## 8. Correctness
Hard constraint in `mv8__RESEARCH_CONTRACT`: exact typed round trip, 0 failed rows in 656 paired rows; every emitted M7 frame passed independent Go decode (`mv8__FINAL_SESSION_REPORT`). Round trip is of the *supported-field* subset; server-derived fields (`event_kind`, `effective_at`, `clock_skew_ms`, `time_quality`) excluded, `sent_at_client` batch envelope reconstructed with a fixed timestamp (`mv8__DATA_INVENTORY`).

## 9. Uncertainty
Repeats are adjacent paired runs minutes apart on one host: bound within-session noise only. Median SD enc 0.0055, dec 0.0088. No p-values claimed. Holdout EXPOSED, no sealed confirmation cohort. Sweep cohort = historical dev; V1 reference is *reconstructed* gzip-1 (118–119 B/event), so "−85%" figures are vs reconstructed V1, not captured traffic.

## 10–11. Implementations
C#: `implementations/research__telemetry-v7__Program.cs` + csproj (stdin JSON → frames; needs `M7*.cs` and native zstd). Go: `research__telemetry-v7__go__main.go` (driver; real decoder is `MortrisV7Data/snapshots/MORTRIS_handoff-v7~/server/internal/transportv7/`, hashes in SHA256SUMS). Python: `src__fhel__problems__telemetry_v7.py` (bridge), `telemetry.py`, `telemetry_code.py` (evaluators; only needed to rerun Heuriva itself).

## 12–14. Device, server, competitor artifacts (not Heuriva's own)
All live in the ignored `MortrisV7Data/` and in `night-run~/`: Unity/Android runs (`night-run~/results/android`, `unity*`), Go/PostgreSQL ingest (`results/server*`), Firebase/GA/Amplitude/Adjust/Facebook comparisons (`results/firebase_wire`, `REPORT.md`, `research/transport-v7/comparison/`). Heuriva only summarizes them (`mv8__PARETO_FRONTIER`).

## 15. Unverified / contradictory
- Heuriva `DATA_INVENTORY`/`EXPERIMENT_LOG` say the night-run report contradicts itself on a physical phone. **Resolution from our side:** the Nothing A142 run was real (adb, added after the night run, §8 of `night-run~/REPORT.md`); the opening "no physical device" scope line predates it and is stale. A correction of that line in `REPORT.md` is still pending (out of Phase 1 scope). Burst-CPU metric definition (raw vs net) is also unreconciled (README of `MortrisV7Data`).
- Corpus line/event counts: 997,076 lines vs 994,564 events vs 991,633 lines in the sibling snapshot — not reconciled.
- Request bytes are application-level at a TLS test receiver; no pcap exists.
- Phone Firebase/Adjust/Facebook wire sizes come from the emulator capture.

## 16. Missing experiments (Heuriva's own list, `mv8__FOUR_HOUR… §9`)
Sealed confirmation cohort with frozen 3–4 candidates; dictionary delivery + full request bytes for 16/32 KiB; repeats across sessions/second host; device-class CPU; allocations/GC; server decode cost of the candidates. Do not run more M7 repeats of known candidates; the remaining 44 unmeasured configs are low-information.

## 17. Integration opportunities
See `INTEGRATION_CANDIDATES.md`.

## Do-not-repeat list
- Rerunning 100/32/base/fixed or 300/32/both/fixed paired CPU on the same macOS host (18 / 13 rows exist).
- Batch 25–50 without dictionary.
- "Larger dictionary removes `both` encode penalty" — disproved.
- Any claim "V8 beats M7": no V8 algorithm exists, only M7 parameters (`mv8__PARETO_FRONTIER`: "No unified V8 frontier is established").
