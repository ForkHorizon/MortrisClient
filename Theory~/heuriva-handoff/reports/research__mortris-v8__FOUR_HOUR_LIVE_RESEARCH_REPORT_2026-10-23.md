# MORTRIS V8 — four-hour live research report (campaign 2026-10-23/24)

Campaign `mortris-v8-day-20261023`: Luna (`gpt-6-luna`, high) directing Heuriva Architecture V2 over the frozen MORTRIS M7 data-only domain. Companion engineering report: `docs/architecture-v2/FOUR_HOUR_LIVE_FIELD_REVIEW_2026-10-23.md`. Numbers are extracted from persisted study databases and `knowledge.sqlite3` by `scripts/campaign_facts.py`; raw telemetry stays local. **Everything below is development-cohort evidence; the holdout is exposed and there is no confirmation cohort.**

## 1. Scientific objective

Find M7 parameter variants that lower payload bytes/event and/or encode/decode CPU relative to the frozen M7 default (batch 100, dictionary 0 KiB, model `base`, batching `fixed`; 23.883 B/event), with exact typed round trips, on the development cohort. Domain: 7 batch sizes x 3 dictionaries x 4 models x 2 batching modes = 168 configurations. This is M7 parameter exploration, **not** a new V8 codec.

## 2. Starting state

Before this campaign: an earlier exploratory campaign (102 unique configurations, 157 measurements) with a best payload reduction of about 27.6 % against the M7 default. Those historical results are not counted as new here. Neither the previous results' per-configuration data nor their CPU uncertainty were loaded into this campaign's knowledge store (it started empty; the supervisor's carry-over covered configurations measured by earlier studies in its own directory only).

## 3. New research performed

- Luna calls: 84 (83 ok). Proposals: 42 `measure`, 33 `explore`/experiment, 12 empty. Two mission rounds ended on rejected proposals.
- Legacy `explore` studies (s1, s5): 136 development measurements over **117 unique configurations**; 19 of the 29 configurations explored in s5 repeated s1 (not intended replication).
- Direct `measure` path: 158 paired rows over **41 unique configurations**, 0 failed, 0 duplicate rows; runs: 11 compare, 16 explore, 6 replicate, 1 investigate.
- Union: **124 of 168 configurations measured** (74 %); 34 measured by both paths; 44 never measured.
- Luna's directions, as recorded in its hypotheses (paraphrased from the director log): (a) does any configuration beat the default on bytes or CPU (answered yes, many); (b) replicate the payload leader and test session batching (300/session/32/both); (c) look for lower-encode-CPU variants at small batches (50/32/base); (d) search a 50–200 batch, 32 KiB dictionary region across base/string/integer models for a joint gain; (e) test large batch with string model for the decode-CPU side. The model did react to the CPU/bytes tradeoff, repeatedly citing the 27.57 % / 1.274x versus 6.49 % / 0.991x contrast.
- Abandoned: none were declared; the final rounds replicated the payload leader instead of opening a new region.

## 4. Best candidate results

Bytes/event relative to the frozen default (23.883 B/event); CPU ratios are candidate/reference from paired runs (1.0 = same); mean ± sample SD over repeats within the campaign. Correctness: exact round trip required by the evaluator; no failed rows. All rows below are from this campaign.

| Candidate (batch/dict KiB/model/batching) | B/event | vs M7 | Encode CPU | Decode CPU | Repeats | Evidence status |
|---|---|---|---|---|---|---|
| 300/32/both/fixed | 17.30 | -27.57 % | 1.274 ± 0.012 | 1.038 ± 0.024 | 13 | exploratory, repeated, dev only |
| 200/32/both/fixed | 17.40 | -27.13 % | 1.224 ± 0.006 | 1.041 ± 0.013 | 3 | exploratory |
| 300/32/integer/fixed | 17.77 | -25.59 % | 1.236 ± 0.002 | 1.020 ± 0.010 | 3 | exploratory |
| 300/32/string/fixed | 18.31 | -23.36 % | 1.119 ± 0.017 | 0.986 ± 0.013 | 8 | exploratory, repeated |
| 150/32/base/fixed | 19.11 | -19.97 % | 1.021 ± 0.002 | 0.998 ± 0.015 | 3 | exploratory |
| 100/32/base/fixed | 19.49 | -18.39 % | 0.996 ± 0.005 | 1.019 ± 0.008 | 3 | exploratory |
| 100/16/base/fixed | 20.01 | -16.21 % | 0.996 ± 0.004 | 1.016 ± 0.007 | 3 | exploratory |
| 50/32/base/fixed | 22.33 | -6.49 % | 0.991 ± 0.009 | 1.089 ± 0.018 | 12 | exploratory, repeated |
| 500/32/base/fixed | 19.42 | -18.69 % | 1.127 ± 0.003 | 0.974 ± 0.005 | 5 | exploratory |

In the explore path single-run points reached -29.66 % (300/32/both/fixed), -28.89 % (500/32/both/fixed) and -28.85 % (500/32/both/session). The explore path uses a geometric payload ratio and the measure path pooled bytes/event, so the two are not interchangeable (the same candidate shows -29.66 % versus -27.57 %). Single-run explore values were not repeated except where listed above; I treat them as screening only.

## 5. Pareto frontier

Among the 40 candidates with at least 3 paired repeats, 26 are non-dominated on (bytes, encode CPU, decode CPU) — a large frontier, which reflects that bytes and CPU trade against each other rather than that many candidates are good. Highlights:

- **Minimum payload:** 300/32/both/fixed (-27.57 %), at +27 % encode CPU and +3.8 % decode CPU. Single-run explore points up to about -29.7 % need repetition.
- **Minimum encode CPU:** among repeated candidates 50/32/base/fixed (0.991) and 100/32/base/fixed, 100/16/base/fixed (0.996); the differences from 1.0 are within a few SD. Among single-run explore rows 50/16/base/session reached 0.986; unreplicated.
- **Minimum decode CPU:** 500/32/string/fixed (0.975) and 500/32/base/fixed (0.974); explore single-runs reached 0.909 (500/16/string/fixed) without repetition.
- **Balanced:** 100/32/base/fixed — 18.4 % fewer bytes with encode CPU 0.996 ± 0.005 and decode 1.019 ± 0.008 — is the candidate that costs the least CPU for the largest payload saving found with repeats. 150/32/base/fixed (-20.0 %, encode 1.021) is the next step on that curve. 300/32/string/fixed gives -23.4 % with decode below reference but encode +12 %.
- **Reliability:** all measured rows round-tripped; no failed measurements.

## 6. Statistical analysis

- Repeats: 3 for 33 candidates, 5–13 for 6, 2 for one. Repeats are paired adjacent runs on one host in minutes, so they estimate within-session CPU noise, not run-to-run, host-to-host or thermal variance.
- CPU noise: SD of the ratio is 0.001–0.017 for most repeated candidates; the explore baseline row against itself measured 1.012, i.e. about 1 % of single-run noise or systematic offset. No p-values or significance claims are made; "below 1.0" is treated as indistinguishable unless the gap is several SD with repeats.
- Limits: one macOS host; host load was not controlled beyond one worker; the dataset is a single frozen development cohort (puzzle-1m, sha256 `8475bd3d…56ca3`); bytes are payload bytes only.
- Inconclusive: encode-CPU improvements of 0.4–1 % at small batch sizes; all single-run explore CPU numbers; the effect of `session` versus `fixed` batching (differences within noise for most pairs).

## 7. Progress relative to previous work

- Previously unmeasured configurations: unknown in absolute terms, because the previous per-configuration set was not loaded here. Within this campaign 124 of 168 were measured; the union with the earlier 102 was not computed.
- Improved previous best payload? **No.** The best repeated value (-27.57 %, 13 repeats) matches the earlier ~27.6 % rather than exceeding it. Single-run explore values up to -29.66 % are unconfirmed and use a different metric.
- Better balanced configuration? **Candidate, not established:** 100/32/base/fixed (-18.4 % bytes, encode ~1.0, decode +1.9 %). A 3-repeat result on one host.
- Did evidence overturn assumptions? Partially: larger batch sizes (300–500) with the 32 KiB dictionary give most of the payload saving, and the string model recovered decode CPU; neither is new to M7.
- Useful new hypotheses from Luna: the tradeoff-focused follow-ups were coherent, but they were refinements of known M7 axes.
- Unproductive directions eliminated: batch 50 without a dictionary regressed payload by about +14 % to +16 % in single-run explore rows (other regions only improved or were neutral).
- Materially advanced V8, or only expanded M7 parameter coverage? **Mostly coverage and repetition.** It supplied repeated paired CPU numbers for about 40 configurations; it did not create a new codec.

## 8. What is still missing

Independent confirmation cohort; Android/device measurements (host CPU is not mobile CPU); allocations and GC; dictionary delivery and update cost (the 16/32 KiB gains ignore it); full request/network bytes (payload only); server decode cost; V8 candidate generation beyond M7 parameters.

## 9. Scientific next steps

1. Seal an untouched confirmation cohort, freeze 3–4 candidates (100/32/base/fixed, 150/32/base/fixed, 300/32/string/fixed, 300/32/both/fixed) and the reference before looking at it.
2. Measure dictionary delivery cost and total request bytes for the 16 and 32 KiB variants.
3. Repeat the balanced candidates across separate sessions and a second host to bound CPU noise.
4. Run the same candidates on a device-class CPU.
5. Only then spend more model calls; the remaining 44 unmeasured configurations are low-information next to the above.

## 10. Final scientific conclusion

**`EXPLORATORY_PROGRESS`.** The campaign produced repeated development-cohort evidence (up to 13 paired repeats) that confirms the earlier ~27.6 % payload reduction and identifies a repeated near-CPU-neutral candidate, but it does not exceed the previous best, uses an exposed holdout, and has no untouched confirmation. `REPEATED_DEVELOPMENT_EVIDENCE` would require the earlier results to be reproduced under identical protocol in the same store, which was not done; `INDEPENDENTLY_CONFIRMED_IMPROVEMENT` is not supported.
