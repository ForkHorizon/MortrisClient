# MORTRIS V8 — scientific reconciliation of the four overnight attempts (2026-10-24)

No eight-hour campaign was completed. This document reconstructs what the four attempts actually measured, from persisted evidence only (`.local/mortris-v8/night{,2,3,4}-campaign-20261024/`: ledgers, `director.jsonl`, `knowledge.sqlite3`, per-round study databases). **No new model calls were made to write it.** Everything is development-cohort evidence on the frozen M7 default (batch 100, dictionary 0 KiB, model `base`, batching `fixed`; 23.883 B/event on the development cohort, dataset sha256 `8475bd3d…56ca3`); the holdout is exposed and there is no confirmation cohort. No new V8 algorithm was tested: every candidate is an M7 parameter combination.

## 1. What each attempt did

| Attempt | Launch → stop (local) | Luna calls | Rounds | Proposals (measure / explore) | Distinct hypothesis ids | Stop |
|---|---|---|---|---|---|---|
| night 1 | 04:08 → 04:22 | 18 | 2 | 18 / 0 | 17 | `repeated_planner_untrusted` |
| night 2 | 04:48 → 06:56 | 118 | 15 | 88 / 5 | 85 | `repeated_planner_untrusted` |
| night 3 | 06:58 → 07:52 | 67 | 7 | 49 / 6 | 54 | `repeated_planner_untrusted` |
| night 4 | 08:11 → paused ≈10:55 | 209 | 16 | 158 / 26 | 169 | none (paused, then closed — see report A) |
| **sum** | | **412** | 40 | 313 / 37 | | |

(Proposals counted from `director.jsonl`; many proposals were refused at admission, so they are requests, not experiments. The 4 attempts had separate 480-call ceilings.)

## 2. Evidence base and what is new

Carry-over was by copying the knowledge store: night 3 started from night 2's store, night 4 from night 3's, and each re-ingested the study databases of the earlier campaigns.

| Quantity | Value | Note |
|---|---|---|
| paired-measure rows in the night-4 store | 616 | **cumulative**: night 2 = 166, night 3 = 106, night 4 = 344 (by run-id prefix). Night 1's 40 rows are in its own store and are not included |
| paired rows over the four attempts (no double counting) | 656 | 40 + 166 + 106 + 344 |
| paired candidates | 105 | of which 55 with ≥3 rows, 26 at the replication cap (≥15 rows); 0 failed rows |
| single-run explore-study candidates | 139 | from the previous 4 h campaign (117) and night 2's own explore studies; single run, different metric (see §3) |
| configurations covered by the union | 168 / 168 | **coverage is not paired measurement**: 63 configurations have only one explore observation |

Of the 616 rows in the night-4 store, the purposes were explore 154, replicate 386, investigate 40, compare 36. So most of the "science" of the night was repeated measurement of already-explored configurations, not new ground. The previous 4 h campaign (see `FOUR_HOUR_LIVE_RESEARCH_REPORT_2026-10-23.md`) had already reached 124/168 configurations; the overnight attempts added the remaining 44 as single-run or paired points and then repeated.

## 3. Metrics and protocols (never merged)

- `measure` (protocol `paired-adjacent-v1`): bytes/event = pooled payload bytes/event; CPU = candidate/reference ns, paired adjacent repeats, randomized order. A "run" is one measurement task (minutes apart, same host, same night), **not an independent session on another day or machine**.
- `explore` (protocol `explore-study-v1`): bytes/event recomputed from the stored per-instance lists (same definition), CPU = the study's time ratio, one run per candidate. The study's own geometric payload ratio gives slightly different relative savings (e.g. −29.66 % vs −27.57 % for 300/32/both/fixed); the two are reported separately.

## 4. Best candidates (paired, ≥3 rows; M7-relative; mean ± sample SD of the per-repeat ratio)

| Candidate batch/dict/model/batching | B/event | vs M7 | Encode CPU | Decode CPU | Rows (runs) | Status |
|---|---|---|---|---|---|---|
| 300/32/both/fixed | 17.30 | −27.57 % | 1.265 ± 0.013 | 1.031 ± 0.018 | 3 (1)* | exploratory; 13 rows in the previous campaign gave 1.274 ± 0.012 |
| 300/32/integer/fixed | 17.77 | −25.59 % | 1.234 ± 0.005 | 1.029 ± 0.013 | 3 (1) | exploratory |
| 500/32/both/session | 17.91 | −25.02 % | 1.321 ± 0.007 | 1.017 ± 0.009 | 8 (4) | exploratory |
| 300/32/string/fixed | 18.31 | −23.36 % | 1.123 ± 0.005 | 0.985 ± 0.010 | 15 (6) | repeated; decode below reference |
| 150/32/base/session | 19.16 | −19.79 % | 1.016 ± 0.007 | 1.012 ± 0.008 | 15 (6) | repeated; near-neutral CPU |
| **100/32/base/fixed** | **19.49** | **−18.39 %** | **0.997 ± 0.004** | **1.017 ± 0.007** | **18 (6)** | **repeated; best balanced** |
| 100/32/base/session | 19.59 | −17.98 % | 0.998 ± 0.004 | 1.024 ± 0.010 | 15 (6) | repeated |
| 100/16/base/fixed | 20.01 | −16.21 % | 0.997 ± 0.005 | 1.019 ± 0.007 | 15 (6) | repeated |
| 100/0/base/fixed (the M7 default measured against itself) | 23.88 | 0.00 % | 0.998 ± 0.004 | 0.998 ± 0.006 | 5 (1) | noise floor of the method |

\* 300/32/both/fixed has 3 rows in this store because most of its repeats live in the previous campaign's store.

Of the 55 candidates with ≥3 rows, 32 are non-dominated on (bytes, encode, decode). Median per-repeat SD: encode 0.0055, decode 0.0088 (max encode SD 0.031). The default measured against itself has encode 0.998 and decode 0.998, so differences below about 1–2 % are not distinguishable from method noise.

## 5. Answers

- **Did the overnight attempts improve the previous best payload?** No. The best repeated payload remains −27.57 % (300/32/both/fixed, +26–27 % encode CPU), unchanged from the previous campaign.
- **Better balanced candidate?** The earlier candidate 100/32/base/fixed is now supported by 18 paired rows across 6 separate measurement runs: −18.39 % bytes, encode 0.997 ± 0.004, decode 1.017 ± 0.007. That is stronger development evidence than the 3 rows of the previous report, but it is the same candidate and the same host, so it is still exploratory/repeated development evidence, not confirmation.
- **Did additional evidence overturn assumptions?** One refinement: decode CPU of the near-neutral candidates is consistently 1–2 % above the reference (not neutral), while encode is neutral; 50/16/base/session shows the opposite tradeoff (encode 0.99, decode 1.08). Payload-first candidates cost 12–32 % encode CPU.
- **Did Luna generate useful new hypotheses?** It produced coherent follow-ups (cross-session CPU reliability, the batch-size knee between 100 and 300, small-batch decode cost, the unmeasured region), 325 hypothesis ids over the four attempts, most of which were variants of one question; it repeatedly asked to replicate the same neutral candidate until the cap and was refused (see report A, defects D-1, D-2, O-2). Nothing here goes beyond M7 parameter tuning.
- **Eliminated directions:** batch 25–50 without a dictionary (+11 % to +16 % bytes in single-run rows); larger dictionaries do not remove the encode penalty of the `both` model.
- **Did it materially advance MORTRIS V8?** No new V8 result. It improved the *quality* of the existing M7 evidence (CPU noise bounds, repeated candidates) and completed coverage; it did not test a new codec family.

## 6. Limits and unverified items

- Not measured: dictionary delivery cost, framing/request bytes, allocations/GC, Android, server CPU. Host CPU on one macOS machine is not mobile CPU.
- Repeats are within one night on one host: they bound within-session noise only; they are not independent confirmation, and the holdout is exposed.
- `night-campaign` (attempt 1) store and the previous campaign's 13-row candidates are not merged into the 616-row store; their figures above are cited separately.
- The exact per-attempt split of explore-study evidence between night 2 and the previous campaign was not re-derived row by row; counts of 139 / 117 follow `campaign_facts` output.
- The paused night-4 campaign had no final `timing_breakdown`; timing is in report A.

## 7. Conclusion

**`EXPLORATORY_PROGRESS` at best, with a strengthened balanced candidate and an honest `NO_NEW_SCIENTIFIC_RESULT` beyond M7 parameter tuning.** The most valuable next experiments (unchanged from the previous report) are not more M7 repeats: seal a confirmation cohort, measure dictionary delivery and full request bytes, repeat the 3–4 frozen candidates on a second host and a device-class CPU, and only then consider a genuinely new candidate family.
