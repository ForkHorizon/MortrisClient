# Architecture V2 — four-hour live field review (campaign 2026-10-23/24)

Campaign `mortris-v8-day-20261023`, Heuriva `main` at `f7f96e9` (PR #23 merged, CI green on that commit). Data-only, Luna (`gpt-6-luna`, effort `high`) through `codex-exec`, subscription route, provider spend $0.
All numbers come from persisted evidence in `.local/mortris-v8/day-campaign-20261023/` (ledgers, director logs, study databases, `knowledge.sqlite3`, `assessments/`, `heartbeats.jsonl`, `timing_breakdown.json`), extracted deterministically by `scripts/campaign_facts.py` (output kept next to the evidence as `facts.json`). Raw evidence stays out of Git. Judgements are marked as such.

## 1. Executive summary

- **Outcome:** the campaign ran unattended from launch to `all_authorized_segments_completed` with **0 recoveries, 0 hard stops, 10 assessments (all `progressing`), 290 heartbeats**. It did **not** use the full authorized window and should not be called a full four-hour run (see §2).
- **Did V2 work with real Luna? Largely yes.** The derived strict output schema was accepted by the real Codex CLI (83 of 84 calls ok, the one failure a 180 s timeout). Luna used both the new `measure` action (42 proposals) and legacy `explore` (33 proposals), read the knowledge store, and built replication and comparison follow-ups on its own. The measure path produced 158 paired rows with 0 duplicate rows and 0 failures.
- **Most important successes:** schema/vocabulary round trip with the real model; zero measurement failures (the previous campaign had four failed studies from model-chosen step counts — none here); durable supervisor with 20-minute assessments that ran without the chat; evaluator and dataset identity held.
- **Most important failures (best-supported hypotheses, not all proven):**
  1. Four segments (s2, s3, s3r1, s3r2) ended because the gateway returned `over_limit` and the controller fell back to `stop`, which was then classified as the *success* kind `program_coverage_achieved`. Director input size at the last reservation was 23 995 / 19 480 / 22 901 / 22 230 bytes against `max_input_bytes = 24000` (s2 was within 5 bytes of the cap). The cause (input cap versus another `over_limit` reason) is **not proven**: the refusal reason is not logged.
  2. Two mission rounds (s4r1, s5r1) stopped with `planner_untrusted` after repeated rejected planner actions; several rejections were `propose` actions with an empty `proposal`.
  3. The legacy `explore` path does not feed the knowledge store, so Luna re-explored configurations already explored: 19 of the 29 configurations explored in s5 had already been explored in s1.
  4. The time breakdown only attributes 2 282 s of measure-path work to execution and init; most of the 11 384 s worker wall time sits in the legacy study path and is not broken down.
- **Classification:** `ARCHITECTURE_LIVE_OPERATIONAL` (see §11). Not `READY_FOR_EXTENDED_RESEARCH`: items 1–3 should be fixed first.

## 2. Campaign lifecycle

| Item | Value |
|---|---|
| Authorization | 4 h, 240 calls, 5 segments x 48 calls x 2 880 s, digest `b69d142a…c365b`, approved by the operator in chat |
| Declared `start_epoch` | 2026-10-23 23:18:59; `end_epoch` 2026-10-24 03:18:59 (policy allows launch up to 1 h before `start_epoch`) |
| Actual launch | 22:54:43; supervisor finished 02:32:21 |
| Actual wall time | 3 h 37 m 38 s (13 058 s). `timing_breakdown.json` reports 11 602 s because it counts from the declared `start_epoch` |
| Unused authorized time | about 46 min before the absolute deadline |
| Segments / rounds | 5 slots, 12 mission rounds (s1:1, s2:1, s3:4, s4:3, s5:3), 12 spawns |
| Round end reasons | 8 x `program_coverage_met`, 2 x `finalization_reserve` (s3r3, s4r2), 2 x `planner_untrusted` (s4r1, s5r1) |
| Final outcome | `all_authorized_segments_completed` |
| Human intervention | one: the digest approval before launch. None during the run |

Why it ended early: all five slots finished (segments end on coverage, not on remaining time), so the supervisor concluded. The 240-call envelope was not the limit: 84 calls were reserved (35%).

## 3. Model operation

- Calls reserved/finished: **84 / 84**; ok **83**; failed **1** (`invocation_timeout`, 180.27 s, in s2).
- Mean latency 16.4 s; max 180.3 s (the timeout). Per segment: s1 2, s2 16, s3 9, s3r1 10, s3r2 5, s3r3 2, s4 3, s4r1 9, s4r2 8, s5 6, s5r1 7, s5r2 7.
- Director decisions: 60 deterministic-trivial (single admissible task, no model call), 83 gateway-ok, 4 `provider_unavailable` (`codex-exec returned over_limit`, one each at the end of s2, s3, s3r1, s3r2).
- Gateway actions: 81 `propose` (42 `measure`, 33 `experiment`, 12 with no proposal), 2 `stop`.
- Invalid schemas: **none observed**; the first reserved call in s1 was a valid structured answer. Admission rejections: the first s1 proposal carried a `purpose` field inside an `explore` action (not a field of that action) and the second call re-proposed without it; I infer the first was refused, but the refusal itself was not read from a log. Total rejection count per call is not stored as a counter — only the 2 `mission_stop` events with "too many rejected planner actions" are directly countable. This is a measurement gap (§8, W-6).
- Route provenance (from the manifest): model `gpt-6-luna`, provider `codex-exec`, effort `high`, per-call timeout 180 s, soft/hard invocation limits 40/48, input cap 24 000 B, output cap 8 000 B. Reasoning content was not inspected.

## 4. Monitoring and recovery

- Assessments written by the supervisor: **10** (interval 1 200 s via `--assess-seconds 1200`). All verdicts `progressing`; assessment 8 recorded `no_useful_work_available` as activity state while still `progressing` (a segment boundary).
- Heartbeats: **290** between 22:54:44 and 02:31:36 (about one per 45 s).
- Stalls detected: 0. Recovery attempts: 0. Recovery journal: 12 `segment_created`, 12 `spawn`, 12 `segment_end`, 5 `slot_complete`, 1 `domain_probe`, 1 `campaign_end`.
- Not exercised: crash recovery on the real controller (no crash occurred); the real-run recovery path remains demonstrated only by the earlier acceptance test.
- Missed failures: the `over_limit` fallback stop was **not** surfaced by monitoring because it was classified as a coverage success. The assessments themselves were deterministic scripts, not an AI review.
- Out-of-band watch by Claude: a poll on the assessment directory and `supervisor_state.json`; it raised nothing beyond the supervisor's own data.

## 5. Research memory

- Knowledge store: 158 measurement rows, 41 unique candidates, 46 runs (12 briefing, 11 compare, 16 explore, 6 replicate, 1 investigate), 0 failed rows, **0 duplicate rows** for the same run/repeat. The store persisted across all 5 segments and 12 rounds (the Director saw prior frontier values: e.g. in s4r1 and s5r1 it quoted 27.57 % and 23.36 % payload reductions and 6.49 % for 50/fixed/32/base).
- Deduplication: `measure` runs requested 55 configurations-repeats, admitted 52, skipped 3 duplicates (`explore` purpose). Intentional repeats (compare/replicate/investigate) were admitted as requested.
- Gap (demonstrated): the legacy `explore` studies are stored in per-segment `campaigns.sqlite3` and are not ingested into `knowledge.sqlite3`. Union of both sources: 124 unique configurations out of the 168-point domain; 34 appear in both; 44 never measured. Within the explore path, s5 re-explored 19 configurations from s1.
- Context growth: Director input grew to 17–24 kB per call, apparently bounded by the 24 000-byte cap. Summaries seem to keep the frontier but this was not audited for omissions.

## 6. Performance breakdown (from `timing_breakdown.json` and the knowledge `runs` table)

| Component | Seconds | Note |
|---|---|---|
| Campaign elapsed (declared start) | 11 602 | actual wall 13 058 |
| Mission wall | 12 770 | sum over 12 rounds |
| Worker wall | 11 384 | includes the legacy explore studies |
| Worker execution (measure path) | 2 108 | 34 non-briefing runs |
| Worker init | 235 | 12 briefing runs account for about 61 s |
| Model decision time | 1 375 | 84 calls |
| Controller overhead | 10.9 | |
| Idle | 0.0 | |
| Recovery wait | 0 | |

Measure-path execution is only about 18 % of worker wall time; the rest is the explore path, whose internal time is not broken down (the breakdown only instruments the measure worker).

## 7. Comparison with the previous campaign (workloads differ; no controlled speedup claimed)

| Metric | Previous (82.5 min) | This campaign |
|---|---|---|
| Authorized time used | 82.5 of 240 min | 217.6 of 240 min wall |
| Luna calls | 26 | 84 (1 timeout) |
| Failed studies from model-chosen step counts | 4 | 0 |
| Accidental repeated measurements | 55 repeated of 157 (35 %), partly intentional | measure path 0 duplicate rows; explore path 19 of 136 rows (14 %) re-explored; intentional repeats 117 measure rows |
| Unique configurations | 102 | 124 (union; not all new relative to the previous 102) |
| Startup overhead | 61 % startup/seed-study | init 235 s of 11 384 s worker wall (2 %); briefing 12 x 5 s |
| Resource limits chosen by model | yes | no (trusted planning; no step failures) |
| Premature termination | not applicable | 4 segments ended by `over_limit` fallback (see §1) |

Interpretation: the failure class "model-controlled step counts" is gone; memory transfer works for `measure`; duplicate work remains in `explore`; throughput of `measure` was not isolated from the mixed workload.

## 8. Architecture weaknesses

| ID | Sev | Symptom | Best-supported cause | Evidence | Impact | Fix |
|---|---|---|---|---|---|---|
| W-1 | P0 | Segments end as `program_coverage_met` after an `over_limit` fallback | the Director input approaches `max_input_bytes` 24 000 and a refused call becomes a `stop`, classified as a success | last reserved input_bytes 23 995 (s2), 22 901, 22 230, 19 480; 4 `provider_unavailable` with `over_limit` | research stopped early and silently; science verdict wrongly "complete" | log the refusal reason; classify a gateway fallback stop as `operator_action_required`/retry, never as coverage; budget and truncate the context to the cap; test with a context near the cap |
| W-2 | P1 | `explore` results never reach the knowledge store | explore studies live in per-segment study DBs | 19 of 29 s5 configs already explored in s1; union 124 vs 41 in the store | duplicate work, memory blind spot | ingest study measurements into `campaign_knowledge` (same context identity) or retire `explore` for the M7 domain in favour of `measure` |
| W-3 | P1 | 2 rounds stopped as `planner_untrusted` | repeated rejected planner actions, including `propose` with no proposal | `mission_stop` in s4r1 (920 s left), s5r1 (1 537 s left) | lost time | return admission errors to the Director in the next context; refuse empty proposals in the schema with a structured retry |
| W-4 | P1 | Luna mixed fields across actions (a `purpose` in `explore`) | one union `params` schema for all actions | s1 first proposal | wasted call | per-action sub-schemas via `oneOf` if Codex strict mode allows |
| W-5 | P2 | Timing breakdown hides most worker time | only measure runs are instrumented; elapsed counted from declared start | 2 282 s of 11 384 s attributed | blind spot in efficiency analysis | instrument explore studies; report wall from actual launch |
| W-6 | P2 | No counter for admission rejections per call | rejections only appear in events | requires scraping | monitoring gap | add `rejected_proposals` to assessments |
| W-7 | P2 | Metric mismatch between paths | explore uses geometric payload ratio; measure uses pooled bytes/event | (300,32,both,fixed): -29.66 % explore vs -27.57 % measure | confusing comparisons | label metrics, report both |
| W-8 | P3 | Supervisor can launch before declared `start_epoch` | policy allows 1 h of early start | launch 24 min early | timing records disagree | record the actual start in the state file |

## 9. Recommended improvements

- **P0:** W-1.
- **P1:** W-2, W-3, W-4.
- **P2:** W-5, W-6, W-7.
- **P3:** W-8; independent confirmation protocol; device-side measurement (not an architecture defect, a research gap).
Complexity: W-1 small-medium (classification plus context budgeting plus tests); W-2 medium (one store); W-3 small; W-4 small if Codex strict schema supports `oneOf`, otherwise medium.

## 10. Next roadmap

Demonstrated needs: (1) W-1 fix and a regression test with a near-cap context; (2) one knowledge store for all evidence; (3) admission feedback to the Director. Speculative (not shown by this run): new codec candidate families, multi-objective scoring by the model, a second evaluator domain.

## 11. Final classification

**`ARCHITECTURE_LIVE_OPERATIONAL`.** Real Luna, the real strict schema, direct `measure`, durable supervision and persistent memory all worked with 0 recoveries needed and 0 measurement failures. It is not `READY_FOR_EXTENDED_RESEARCH` because four of twelve rounds ended through a mis-classified size limit and the explore path bypasses memory. Recovery on the real controller was never exercised in this run.
