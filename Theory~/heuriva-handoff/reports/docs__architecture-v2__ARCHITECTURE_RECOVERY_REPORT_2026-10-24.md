# Architecture recovery and stabilization — report (2026-10-24)

Branch `daliys/fix-over-limit-stop`, PR [#25](https://github.com/ForkHorizon/Heuriva/pull/25). Qualified code commit: `f795857` (`f795857b2337074fc674d80aeb9f934586b0829f`); later commits on the branch only add documentation (this report, the readiness document, the scientific reconciliation). Predecessors: `EIGHT_HOUR_ARCHITECTURE_FIELD_REVIEW_2026-10-24.md` (what happened live), `FOUR_HOUR_LIVE_FIELD_REVIEW_2026-10-23.md` (PR #24). Scientific companion: `research/mortris-v8/OVERNIGHT_RESEARCH_RECONCILIATION_2026-10-24.md`. Launch procedure: `NEXT_EXTENDED_CAMPAIGN_READINESS.md`.

No live model call was made in this task. No campaign was started, resumed or extended. Historical evidence was not edited; the only write to it is one appended `campaign_closed` journal record on the paused campaign (§4).

## 1. Executive summary

- The overnight failure was not one bug. It was five independent defects in the interaction between the Director, the trusted admission layer, the mission template and the supervisor's slot lifecycle, plus an accounting gap (four launches = four 480-call budgets). All five have fixes with regression tests; two classes of residual risk remain (§6).
- The P0 lifecycle defect (restart at a slot boundary ended the whole campaign) is **fixed by design**, not by a state edit: slot and campaign endings are now typed (`SlotEnd`), the round counter is rebuilt from rounds recorded as ended, and a slot's verdict is persisted with the slot and re-applied after a restart.
- Budget integrity: an ended campaign can never be reopened; pause/close are first-class operations; related campaigns can share one **group ceiling** that a new directory or campaign id cannot reset (copying an approved authorization elsewhere is refused).
- Rejection handling is typed (`rejection_codes`), not text-matched; progress is measured as information (saturating), with named verdicts; mandatory research goals that can never be satisfied are refused before a campaign starts (templates v3/v4 were exactly that).
- An independent reviewer (separate context, read-only) found 2 P1 and several P2 defects in my first fixes; all confirmed ones were reproduced and fixed (§12).
- I also caused and fixed one incident of my own: I overwrote the existing `src/fhel/admission.py` (resource controller) with new code; the full suite caught it at collection; the file is restored byte-identical to `main` and the new code lives in `src/fhel/rejection_codes.py` (§7).
- **Readiness: `READY_FOR_BOUNDED_LIVE_CANARY`.** Everything verifiable offline passed; changes to the Director context and prompt have not been exercised against the real Codex route.

## 2. Reconstructed timeline (local, 2026-10-24)

| Run | Launch → stop | Calls | Stop reason |
|---|---|---|---|
| previous 4 h (PR #24) | 23.10 23:18 → 02:32 | 84 | completed |
| night 1 | 04:08 → 04:22 | 18 | `repeated_planner_untrusted` |
| night 2 | 04:48 → 06:56 | 118 | `repeated_planner_untrusted` |
| night 3 | 06:58 → 07:52 | 67 | `repeated_planner_untrusted` |
| night 4 | 08:11 → paused ≈10:55 | 209 | closed unresumed in this task |

412 calls over four campaigns; each had its own ceiling (no shared ceiling existed). Cross-checked against the per-campaign ledgers (`spent_total`), `supervisor_state.json` `launched_epoch`/`finished`, and `recovery_journal.jsonl`.

## 3. Root causes (evidence in the field review §5–6)

| Failure | Root cause | Fix |
|---|---|---|
| D-1/D-2 replication loops | duplicate-approach check also applied to stated replications; replication cap invisible to the Director; template v3/v4 contained a required hypothesis with no task | exemption for stated repeats; cap + recent refusals in the Director context; static feasibility check (v3/v4 now refused) |
| D-3 spent round allowance treated as outage | `director call budget exhausted` classified as recoverable `director_unavailable` | typed `round_call_budget_exhausted` → round end (`CONTINUE`) |
| D-4 restart at slot boundary ends campaign | `_run_slot` returned `None` for "no further round fits"; `run()` read `None` as campaign exhaustion | typed `SlotResult`; rounds reconciled; verdict persisted |
| D-6 trust stops on state refusals | every refusal counted as a trust violation | typed `RejectCode`; only feedback codes bypass the trust counter |
| accounting | per-directory ledgers only | optional `group` budget bound to directory + digest, registry, exclusivity |
| false progress | row counts counted as progress | `information_units` with saturation + named verdicts |

Additional root cause (new): the template program was unsatisfiable by construction — every pre-registered hypothesis is `required`, only a task-bound hypothesis can reach `EVIDENCE_VERIFIED`, and Director-proposed hypotheses are never required. A required hypothesis without a task therefore makes coverage unreachable and every round ends "inconclusive". This explains why nights 2–4 never ended on coverage.

## 4. Historical evidence handling

Found all four campaign directories under `.local/mortris-v8/`; no supervisor/controller was running (process list checked). Night 4 was paused with `outcome=None` and 224 min left on its deadline. It was **not** resumed. It was closed with the new `close` command (an appended `campaign_closed` journal record and `outcome=closed_by_operator`; no field was edited by hand). At that moment the command did not yet refuse while a controller is alive (added later after the review); I checked the process list first and none of the campaign was running. The earlier manual `operator_state_edit` in night 3 (clearing an outcome) is recorded in its journal and described in the field review; it is not repeated.

## 5. Implemented corrections (commits on the branch, newest last)

`5f3b3fb` typed route failures + context budget · `14d023e` knowledge unification · `da5fb45` per-action proposals · `ad115a5` assessments · `4fd2d4c`/`214bf71` finalization + facts · `fbe696a` runbook · `cd65991`, `42b92b6`, `68af5c5`, `eeae04a` fixes found by the live runs · `c08c309` field review · `98c5119` slot/campaign lifecycle + group budget · `6c439a5` typed refusals, information progress · `6e8c450` template feasibility · `534a3b7` union decision shape (off) · `f416928` in-flight snapshots · `fc165ee` independent-review fixes · `ccf9266` admission restore · `f795857` suite regressions (qualified).

Changed components: `campaign_supervisor` (SlotEnd/SlotResult, `_reconcile_slot`, `_apply_slot_end`, pause via SIGTERM/SIGINT, `close`, `make-auth --group`, lineage `launches`, login retry, guarded diagnostics, cross-round refusal digest), `campaign_auth` (optional `group`, registry), `rejection_codes` (new), `mission_continuity` (typed refusals, `Action.outage`, `unsatisfiable_now`), `mission_lifecycle` (typed failure kinds), `mission_director` (kinds, context budget), `mission_memory` (`fit_context`), `research_program` (feasibility), `campaign_assess` (information units, verdicts), `campaign_facts`, `measure_worker`/`research_worker` (typed raisers, cap, hints), `model_route_codex` (union shape off by default, prompt guidance), templates v5.

## 6. Remaining gaps (not fixed)

- **Union decision shape is untested on the real route** (default `flat`). Needs a bounded canary.
- Changes to the Director context (`admissible_now`, `recent_refusals`, `replication_cap`) and the prompt text were not seen by the real model.
- Group allowance is checked at round creation; a ledger deleted by hand resets spend (tampering is out of scope); concurrent group campaigns are refused at start only.
- Pause waits for the controller; a model call in flight may be abandoned with an unknown outcome (counted as spent, never replayed). The pause is only observed in the segment loop (not during the 30-min domain probe).
- Empty `propose` is prevented structurally only in the (not yet live-verified) union shape; in the flat shape it is handled by feedback and bounded loops.
- Study evidence is ingested without a dataset-manifest comparison (manifest hashes differ in kind from the file hash).
- No new trusted research capability beyond M7 parameters (§14 of the brief): the missing interface is a second evaluator-registered, data-only candidate family with its own independent decoder; not started because it cannot be done safely alongside the lifecycle work.

## 7. Incident: overwritten `admission.py`

While adding typed refusals I created `src/fhel/admission.py`, which already existed (resource `AdmissionController`). The mistake repeated one made earlier with `lifecycle.py`. The full suite failed at collection (10 errors); I restored the file from `main` (`git diff main -- src/fhel/admission.py` is empty) and moved the new code to `rejection_codes.py`. Lesson recorded: always check for an existing path before writing a new module.

## 8. Authorization and budget integrity

Resume/recover/retry/new are now distinct: resume = same command, same authorization, same deadline (`launches` lineage); recover = bounded by the authorization's recovery policy; an ended or closed campaign refuses to start (`authorization_invalid`); a new campaign needs a new `make-auth` and digest approval and, when it belongs to a group, draws on the group ceiling (`make-auth` refuses when the request exceeds what is left). Default group id = `<operator>-<UTC date>`, default ceiling = the policy maximum for one campaign (480); a higher ceiling must be given explicitly and is part of the approved digest. Blanket chat permission cannot create budget: nothing in the code reads chat.

## 9. Recovery and lifecycle behaviour (tests)

`tests/test_campaign_lifecycle_acceptance.py` (20 tests): death between slot end and outcome; death between a round ending and its counter; calls exhausted in one slot but not the next; campaign ceiling; ended campaign refused; pause + resume (no double count); close; group registration/exclusivity/ceiling; persisted verdicts; login retry; model-text spoof; assessment timer. Crash points are injected through real code paths (the process "dies" at an exact point), never by editing state.

## 10. Monitoring correctness

Assessments carry `health`, `progress{operational, experimental_rows, information_units, unique_configs}`, typed route errors, rejection/replication/duplicate counters, UTC and launch clocks, and a named `verdict` (`HEALTHY_RESEARCH_PROGRESS`, `REPLICATION_IN_PROGRESS`, `ACTIVE_VALID_EXPERIMENT`, `LOW_INFORMATION_REPETITION`, `REPEATED_REJECTION_LOOP`, `NO_NEW_ADMISSIBLE_WORK`, `PROVIDER_FAILURE`, `RECOVERABLE_PROCESS_FAILURE`, `IDLE_NO_PROGRESS`). Snapshots (`finalization/`, `timing_breakdown.json`) are rewritten at every assessment. Information saturates at 9 paired rows per candidate (policy knob), so endless repeats stop looking productive; stagnation (two rounds without information) ends the slot, two such slots end the campaign as `research_opportunities_exhausted`.

## 11. Evidence and scientific integrity

Explore-study evidence enters the knowledge store under its own protocol context, read-only on the legacy databases, idempotent; the two metrics are never merged. The replication cap (15 paired rows) is a trusted limit. Static and runtime template feasibility prevent impossible mandatory goals.

## 12. Security review and independent review

`_benign_rejection` now reads only a machine-generated code; plain strings and unexpected exceptions fail closed. An independent reviewer (separate context, read-only) attacked the branch and found:

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| P1-1 | P1 | group ceiling bypass by copying an approved authorization to an unregistered directory | **fixed** (registration bound to dir + digest; test) |
| P1-2 | P1 | model rationale starting with `director_unavailable: kind=…` selected the lifecycle disposition (could hard-stop the campaign or downgrade met coverage) | **fixed** (typed `Action.outage`, never parsed from model text; test) |
| P2-3 | P2 | slot verdict lost if the process died after the slot was marked ended | **fixed** (re-applied from persisted state; test) |
| P2-4 | P2 | reconciled `FINISH` ignored; streak not rebuilt | **fixed** |
| P2-6 | P2 | `Rejection` lost its code on copy/pickle | **fixed** (`__reduce__`; test) |
| P2-8 | P2 | deterministic Director failures treated as recoverable | **fixed** (round end) |
| P1-7 | P1(s) | transient login probe failure ended the campaign for good | **fixed** (3 spaced tries) |
| P2-10/11/15 | P2 | close with orphan controller; unguarded diagnostics; extra retries on quota error | **fixed** |
| P2-9, 12, 13, 14 | P2 | see §6 | documented, not fixed |
| P2-5 | P2 | flat path changed (per-category union, prompt) without a real-route canary | **open → canary** |

## 13. Acceptance-test results

**Full regression (qualified commit `f795857`)**: `uv run pytest -q` → **1696 passed, 9 skipped, 0 failed** (22 min 17 s); `ruff check src tests scripts` clean; `fhel smoke` → `artifact_verified: true`, `persistent_reopen: true`, `external_calls: 0`. Earlier full runs on the way: 1659 and 1662 passed at `cd65991`/`eeae04a`; a run on `ccf9266` had **8 failures** (`test_mission_continuity` ×6, `test_research_program` ×1, `test_ams_demos[demo9]`) caused by my typed refusals — unknown references and state conflicts had become feedback; they were returned to the trust counter, reports now show benign counts, and the timeout test uses the typed message. The 10 collection errors of the `admission.py` incident (§7) preceded that.

**Lifecycle acceptance (deterministic stub controller, real subprocesses, real files)**: `tests/test_campaign_lifecycle_acceptance.py` — 20 tests, all passing; includes the review-finding regressions. Related: `test_campaign_supervisor.py` (25), `test_context_budget.py`, `test_campaign_assess.py`, `test_knowledge_unification.py`, `test_schema_compat.py`, `test_campaign_facts.py`, `test_research_program.py` feasibility tests.

**Bounded real-clock offline acceptance** (`scripts/unattended_acceptance_v2.py`, provider none, real M7 data, rule Director, template v5, 3 slots x 1200 s), run on the qualified commit `f795857`; evidence `.local/mortris-v8/evidence-accepted/ACCEPTANCE_REPORT_f795857.json`:
- 2 632 s (43.9 min) wall; exit 0; outcome `all_authorized_segments_completed`; 3 slots `slot_complete`, 3 rounds.
- Fault injection: `SIGKILL` of the controller at 150 s → authorized recovery (recoveries = 1, same round resumed); `SIGTERM` of the **supervisor** at 400 s → clean pause (exit 0, no outcome recorded); same command restarted at 420 s → `launches = [start, resume]`, state and deadline preserved, no manual state edit.
- Evidence: 162 paired rows, 162 distinct candidates, **0 duplicate rows**, 0 failures; 0 model calls; 57 heartbeats; timing breakdown present (context construction 0.71 s of 2 627 s, controller overhead 2.0 s, idle 88.9 s, recovery wait 5 s).
- **Limits of this evidence**: only **1** 20-minute assessment was produced (the restart reset the interval before the persisted timer existed in state — the timer now persists after the first assessment, but a restart before the first assessment still restarts it), so the full assessment cadence under restarts was not shown more than once; `monotonic_elapsed_s` (1 216 s) is a lower bound because it is persisted only at assessments; the recovery tested is a controller crash, not a crash of the supervisor mid-write (that is covered by the stub-based tests). An earlier run on `ccf9266` (before the suite regressions were fixed) gave the same lifecycle result (2 587 s, 156 rows, recoveries 1, pause/resume ok); two earlier runs were aborted when the code changed and are kept under `.local/mortris-v8/evidence-aborted/`.
- Not done: no real-model canary (and no new live campaign) in this task, as instructed.

## 14. CI status

Hosted CI (GitHub Actions, job `test` = lint + tests + CLI smoke) on `f795857` (exact PR head at that time): **SUCCESS**. On the previous heads: `c08c309` SUCCESS. The documentation commits added after `f795857` change no code; their CI result is shown on the PR and is not claimed here.

## 15. Operational readiness

`READY_FOR_BOUNDED_LIVE_CANARY`. Not `READY_FOR_EXTENDED_CAMPAIGN`: no run of the final code against the real route, and the first extended run should itself start with a 1–3 call canary under its own authorization. See `NEXT_EXTENDED_CAMPAIGN_READINESS.md`.

## 16. Next engineering priorities

1. Bounded canary (≤3 Luna High calls): current context + prompt with the flat shape; then the union shape.
2. Controller-aware pause that waits for an in-flight model call to finish (or records it as unknown) and covers the probe phase.
3. Group-level reservation (atomic) instead of start-time exclusivity.
4. A second trusted candidate family (data-only transform with an independent round-trip decoder).
5. Seal a confirmation cohort and measure dictionary delivery / framing bytes.
