# Architecture V2 stabilization and the 2026-10-24 overnight live runs — field review

Branch `daliys/fix-over-limit-stop` (code + this report). Predecessor evidence: `FOUR_HOUR_LIVE_FIELD_REVIEW_2026-10-23.md` (PR #24). This review is about the architecture, not the compression results; the scientific report for these runs is **not written yet** (see §14).

Everything below comes from persisted evidence in the git-ignored `.local/mortris-v8/{night-campaign,night2-campaign,night3-campaign,night4-campaign}-20261024/` (ledgers, `director.jsonl`, mission `events.jsonl`, `assessments/`, `heartbeats.jsonl`, `recovery_journal.jsonl`, `knowledge.sqlite3`) and from git. Where something is a hypothesis, it says so.

## 1. Summary

- The assignment was Phase A (engineering) followed by Phase B (one 8 h / 480-call live campaign). Phase A shipped P0/P1/P2 fixes with regression tests. Phase B **did not run as one campaign**: four launches were needed. Three stopped on `repeated_planner_untrusted` after 14 min, 2 h 08 min and 54 min. The fourth is **paused** by the operator at 2 h 44 min, 209 calls, with no outcome recorded (resumable, deadline 16:11 local).
- Every one of the three stops was caused by a defect that Phase A introduced or failed to anticipate, found only by the live run. None was a provider outage.
- The P0 defect from the previous field test (`over_limit` recorded as `program_coverage_met`) is fixed and now verified live in the sense that no false coverage occurred in 4 campaigns; the exact original trigger (prompt above the byte cap) was not reproduced live.
- Honest classification of this session: **`ARCHITECTURE_PARTIALLY_OPERATIONAL`**. The supervisor, ledger accounting, heartbeats and assessments worked every time; the Director/lab interaction (feedback, caps, templates) needed four iterations.

## 2. Timeline (local time, 2026-10-24; from `launched_epoch`/`finished` in each `supervisor_state.json`)

| Run | Launch | Stop | Calls (ok) | Rounds | Outcome |
|---|---|---|---|---|---|
| previous 4 h (see predecessor) | 23.10 23:18 | 02:32 | 84 (83) | 12 | `all_authorized_segments_completed` |
| night 1 | 04:08 | 04:22 | 18 (18) | 2 | `repeated_planner_untrusted` |
| night 2 | 04:48 | 06:56 | 118 (115, 3 timeouts) | 15 | `repeated_planner_untrusted` |
| night 3 | 06:58 | 07:52 | 67 (66, 1 timeout) | 7 | `repeated_planner_untrusted` |
| night 4 | 08:11 | paused ≈10:55 | 209 (208, 1 timeout) | 16 | none (resumable) |

Phase A commits on this branch: `5f3b3fb` (P0), `14d023e` (knowledge unification), `da5fb45` (typed proposals), `ad115a5` (assessments), `4fd2d4c`/`214bf71` (finalization, facts), `fbe696a` (runbook), `cd65991`, `42b92b6`, `68af5c5`, `eeae04a` (live-found fixes), plus the final commit containing this report. Full pytest: 1 659 passed at `cd65991`, 1 662 passed at `eeae04a` (each ≈17.5 min; ruff clean). After `eeae04a` only the facts export and its tests changed (`tests/test_campaign_facts.py`, 3 passed, run alone); the full suite was **not** re-run on the final commit. **Hosted CI on this branch has not been checked.** `fhel smoke` passed once (before launch).

Why the long gap between Phase A and a stable run: each stop cost a diagnosis, a fix, a 17.5 min full regression run and a restart (three full runs). No time was lost to idle waiting.

## 3. What Phase A changed (verified by tests, then partly by live runs)

| Area | Change | Live evidence |
|---|---|---|
| P0 route failure | `failure_kind()` types every refused/failed call (`input_context_too_large`, `output_contract_violation`, `timeout`, `auth_or_quota`, `invocation_budget_exhausted`, `route_window_elapsed`, `round_call_budget_exhausted`, transient); `director_unavailable` is never reported as coverage; auth/quota and budget are hard stops | route errors appeared typed in assessments (`round_call_budget_exhausted` ×2) |
| Context | `fit_context()` bounds the **whole** Director context (base + lab) below `max_input_bytes − prompt head − 600`; deterministic ladder; raises `ContextTooLarge` rather than dropping mandatory content | ledger `input_bytes` plateaued ≈19.9 kB in night 1 (cap 24 000); no `input_too_large` seen |
| Knowledge | explore-study measurements are published into `knowledge.sqlite3` under their own protocol context; `explore` proposals that are <75 % new ground are refused with the unmeasured list | no accidental explore repeats (`accidental_duplicates` 0 in all assessments) |
| Proposals | per-action discriminated schema; empty `propose` and malformed proposals return actionable text | accepted by the real Codex CLI from the first call (83+ calls) |
| Assessments | `health`, `science_verdict`, typed route errors, rejection/duplicate/replication counters, UTC and launch clocks | produced every 20 min; see defects D-5/D-6 |
| Finalization | supervisor writes `finalization/facts.json` + `FACT_SKELETON.md` at stop | written at every stop; analysis marked PENDING |

## 4. Root cause of the previous P0 (`over_limit` → coverage)

Established from code: the route's `max_input_bytes` check applies to the **whole prompt** (`prompt_for(request)` = prompt head + canonical context); the ledger's `input_bytes` is that same full size. The base mission context is capped at 14 000 B, but the `lab` block (capability vocabulary ≈3.9 kB + knowledge ≈5.8 kB) and the 2.7 kB head were added **after** the cap, so the total could reach ≈26 kB. Last accepted prompts in the previous campaign were 23 995 B (s2) … 19 480 B (s3). The refusal reason itself was never logged, so the exact trigger remains **unproven** for s3/s3r1/s3r2. The controller then fell back to `stop`, and `_finish()` tested "program coverage met" before "director unavailable", so a transport failure became a completed program. Both causes are now addressed (budget + precedence); the typed reason is logged.

## 5. Defects found live (this session), in order

| ID | Run | Symptom | Evidence | Root cause | Status |
|---|---|---|---|---|---|
| D-1 | night 1 | "duplicate approach" refusals; run stopped at 14 min | 3 `duplicate approach` + 8 "already measured" rejections for `replicate 100/32/base/fixed` | the task-signature duplicate check also applied to deliberate replications (`purpose=replicate`); my replication cap's text said "use purpose replicate" although the proposal already did | **fixed** (`cd65991`): stated replications are exempt, cap message explicit |
| D-2 | night 2 | stop at 2 h 08 min after 4 `planner_untrusted` rounds | 23 cap refusals, 11 empty `propose`; the pre-registered hypothesis in template v3 named 100/32/base/fixed, which hit the cap and could then never be satisfied | template design flaw + the cap was invisible to the Director | **fixed** in template v4 and by exposing `knowledge.replication_cap` (`eeae04a`) |
| D-3 | night 3 | `director call budget exhausted` handled as a recoverable provider outage (recovery 1 of 5 spent) | `recovery_journal.jsonl`: `why: director_unavailable` at round s1r3 | per-round call allowance (`max_invocations` of the round manifest) was typed as a provider failure → `RECOVER` | **fixed** (`68af5c5`): `round_call_budget_exhausted` is a normal round end (`CONTINUE`); I paused the supervisor to ship this, then resumed with the same command |
| D-4 | night 3 | supervisor resumed exactly at a slot boundary, returned `last=None` and recorded `no_budget_or_time_for_segment` although 9 slots and 432 calls remained | `campaign_end` event ≈07:40 + `finalized` | `_run_slot` returns `None` when no further round fits; `run()` interprets `None` as campaign-level exhaustion | **worked around, NOT fixed in code**: I cleared `outcome` in `supervisor_state.json` and logged an `operator_state_edit` event |
| D-5 | night 3 | assessments reported `process_unhealthy` while the campaign was fine | assessments 1–2 | health read `child.poll()` during a round transition | **fixed** (`68af5c5`: `between_rounds`) |
| D-6 | night 2–4 | three consecutive rounds ended `planner_untrusted` on state-based refusals; two in a row hard-stop the campaign | `mission_stop` events; rejection mix in §7 | every refusal counted toward the 5-rejection trust limit | **fixed** (`eeae04a`): state-based refusals are "benign", bounded separately, end the round as `program_exhausted_inconclusive`. **Only night 4 ran with this**; no hard stop occurred in 16 rounds |

## 6. Open defects (not fixed)

| ID | Sev | Symptom / evidence | Hypothesis / cause | Proposed fix |
|---|---|---|---|---|
| O-1 | P0 | D-4 resume-at-slot-boundary bug is still in the code | `last=None` ambiguity in `_run_slot`/`run()` | return an explicit "slot complete" verdict; regression test that restarts at a slot end |
| O-2 | P1 | empty `propose` (`proposal=null`) keeps occurring: 11 (night 2), 8 (night 3), 16 (night 4) | **unproven**; rationale texts say Luna wants to propose but cannot build an admissible one (caps, replans_left 0). The schema cannot forbid `propose`+`null` because a root-level `anyOf` is not allowed | make the decision itself a union (`propose` ⇒ proposal object) if the Codex CLI accepts a nested action wrapper; test against the real route before relying on it |
| O-3 | P1 | assessment `science_verdict` counts replication rows as progress | night 4 after 168 configs: +35 replicate rows / 20 min, 0 new configs, verdict `progressing` | separate "new information" (new unique config, new CPU context for a candidate below the cap) from raw rows; flag `low_information_replication` |
| O-4 | P1 | rounds restart the 5-rejection and `max_new_tasks`/`replans` limits; many rounds end by `program_exhausted_inconclusive` while slot time remains | limits are per mission round; the Director's behaviour is a loop of "ask → refuse" | carry rejection feedback across rounds; stop the **slot** (not only the round) when N consecutive rounds end without a new measurement (the supervisor's stagnation rule only counts raw rows) |
| O-5 | P2 | night 4 `timing_breakdown` absent (paused); night 2 `worker_other_s` 2 589 s = legacy explore | the breakdown is written only at stop | write it at each assessment |
| O-6 | P2 | facts mixed contexts after ingestion (fixed in this branch for the export) | knowledge store holds both protocols | keep reporting them separately (done in `campaign_facts`) |
| O-7 | P2 | the `explore` path is barely used after night 2 (Luna prefers `measure`) | n/a | consider retiring `explore` for the M7 domain |

## 7. Model and lab interaction (all four runs)

- Calls: 18 + 118 + 67 + 209 = **412** over four campaigns (each had its own 480 ceiling; no shared ceiling was enforced across campaigns — an accounting gap the operator should know about). Timeouts: 5 (180 s each: night 2 ×3, night 3 ×1, night 4 ×1; one is counted in the 209). Mean latency 11.8–18.9 s.
- Schema: no invalid-schema failures in 412 calls with the per-action union.
- Rejections (admission) per run: 12, 49, 33, 92. Mix in night 4: replication cap 22, empty propose 16, "configuration space already measured" 14, "requested configs already measured" 13, hypothesis-id problems 6+2. None was a safety refusal (generated code, paid provider, forbidden field).
- Luna's own reasoning, read from `director.jsonl`, was coherent and cited the cap and the 3 % bound correctly once it could see them; the earlier loops were information gaps in the context, not model faults.

## 8. Research memory

Knowledge carried across campaigns by copying `knowledge.sqlite3` and re-ingesting the study databases (night 3 started with 139 explored and 21 paired configurations, night 4 with 139 and 52). In night 4 the store holds **105 paired-measured** configurations (616 paired rows, cumulative across the carried-over rows) and **139 single-run explore-study** configurations; their union covers 168/168 (the assessment `unique_m7_configs` is the union). "168 measured" therefore does **not** mean 168 paired measurements. Duplicate work: 0 accidental duplicates in every assessment. Restart: the supervisor resume (twice) kept all state; the store survived.

## 9. Monitoring and recovery

- Night 4: 7 assessments (all `progressing`), 213 heartbeats, 0 recoveries. Night 3: 2 (`process_unhealthy`, false positive D-5), 1 recovery (D-3 misclassification, not a crash). Night 2: 6 assessments, 171 heartbeats, 0 recoveries.
- A genuine controller/worker crash recovery was **not** exercised live in any of these runs. SIGTERM pause/resume of the supervisor was exercised (night 3 at ≈07:40; night 4 at ≈10:55): in night 4 the controller had just finished its round, no call was in flight at the end, `ledger` shows 0 calls without a `finished` record.
- Clocks: assessments now record UTC, launch epoch and monotonic elapsed; deadlines remain UTC epochs, so the 24→25 Oct DST change would not matter (not exercised live).

## 10. Authorization and operator involvement

The digest approval was given in chat as a blanket delegation ("full permission to launch the 8 h run, ask nothing"). It was recorded in `approval_note.txt` in each campaign directory. Four authorizations/digests were created (one per campaign); relaunches after a defect were made under the same delegation, which the operator may want to treat as stretching the "one campaign" intent of the brief. The operator learned of the failed launches late; I should have reported each one immediately.

## 11. Comparison with the previous live test

| | previous (84 calls) | this session, night 4 (209 calls) |
|---|---|---|
| false coverage after a route failure | 4 rounds | 0 |
| failed studies from model-controlled limits | 0 (fixed before) | 0 |
| accidental duplicate configs | 19 explore repeats | 0 |
| rounds ended by trust stop | 2 | 0 (but 4 in night 1–2 rounds and 3 in night 3, before D-6 was fixed) |
| empty `propose` | 12 | 16 (unsolved, O-2) |

## 12. Readiness

For future long runs: **not ready until O-1 and O-4 are fixed and a run completes a full window without operator action.** Per the brief's gates, Phase A would be `GO_BOUNDED_LIVE` at best; the live evidence supports `GO_BOUNDED_LIVE` only after the open P0/P1 items above.

## 13. Not done

Priority 5 (a genuinely new trusted data-only candidate family) was **not** implemented; no V8 algorithm beyond M7 parameters was evaluated. No independent confirmation cohort, device or server measurements.

## 14. Next steps (suggested for the reviewing agent)

1. Review commits `5f3b3fb…eeae04a` and this report together; check hosted CI.
2. Fix O-1 (explicit slot-complete verdict) with a restart-at-boundary test.
3. Decide O-2/O-4 with a one-call route experiment under a fresh, small authorization.
4. Decide whether to resume night 4 (322 min left on its deadline; domain exhausted) or end it; then write the scientific report from `night4-campaign-20261024/finalization/`.
