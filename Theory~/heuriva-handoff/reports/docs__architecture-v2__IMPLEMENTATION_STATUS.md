# Architecture v2 - implementation status

Legend: P proposed . I implemented . L locally tested (unit/integration, offline) . R real-data offline run (no model) . CI hosted CI verified . LIVE live Luna tested . S scientifically validated . NQ not yet qualified.
Nothing is CI verified (local branch), nothing is live tested, nothing is scientifically validated.

| WP | Deliverable | I | L | R | CI | LIVE | S | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | Typed capability contract (`research_contract.py`); schema, vocabulary, admission derived from it; structured params | yes | yes | yes | no | **no** | n/a | strict schema never sent to the real Codex CLI; contract covers M7 + legacy code lab only |
| 2 | Operational limits removed from model control; trusted derivation and cost overwrite | yes | yes | yes | no | no | n/a | operator documents keep explicit control; `code_research` keeps its legacy `max_iterations` field (domain parameter, not a lifecycle limit) |
| 3 | Campaign knowledge store, context identity, dedupe, replication, restart safety | yes | yes | yes | no | no | n/a | `explore` studies are not imported into the store |
| 4 | `measure` (exact configs, repeats, compare/investigate purposes, briefing); `explore` kept | yes | yes | yes | no | no | n/a | actions F (hypothesis) via existing proposal.hypothesis; G (design candidate) and H (structured conclude) **not implemented** |
| 5 | Uncertainty, evidence ladder, Pareto, missing-data semantics | yes | yes | yes | no | no | **no** | no statistical test, no practical thresholds, allocations/device/server/dictionary-cost not measured |
| 6 | Typed lifecycle (`mission_lifecycle.py`), `routine_failures`, rounds in slots, cumulative ledgers, honest early conclusion | yes | yes | yes | no | no | n/a | mission identity not literally continuous across rounds (route manifest binds one mission) |
| 7 | No seed studies (free briefing), pre-run dedupe, domain probe (`domain_probe.py`, run once by the supervisor), timing breakdown | yes | yes | yes | no | no | n/a | probe covers axis extremes only, on 4 installations |
| 8 | Evaluator lock (`evaluator_lock.py`): frozen ids + content-addressed sources, drift detected before each round and assessment | yes | yes | yes | no | no | n/a | detection and reproducibility, **not** execution isolation; reference generalisation (without a Problem class) not done |
| 9 | Agent-role decision (documented in OVERVIEW) | yes | n/a | n/a | n/a | n/a | n/a | decision, not code |

## Reconciliation of proposal-refusal counts
The first campaign report said 0 refusals because it read only `director.jsonl`. Persisted per-segment `events.jsonl` records `action_rejected` for **6 of 21** gateway proposals (4 "space already measured", 2 "malformed proposal": `propose` with no body); 15 were admitted. The earlier pilot-1 count (6 of 6 refused) was a different cause (missing vocabulary) and is fixed.

## Components changed
New: `research_contract`, `campaign_knowledge`, `measure_worker`, `mission_lifecycle`, `evaluator_lock`, `domain_probe`, `scripts/unattended_acceptance_v2.py`, `research/mortris-v8/campaign_template_v2.json`. Changed: `mission_continuity` (category `measure`, bounded structured params, `routine_failures`), `mission_director` (proposal finalizer), `mission_ops` (wiring, vocabulary, knowledge context, offline rule follow-up), `model_route_codex` (schema derived), `research_worker` (derived limits, dict space, knowledge-aware admission), `research_program` (`measure` is an evidence category), `external_entry` (`measure_batch`), `campaign_auth` / `campaign_supervisor` (rounds, typed verdicts, accounting, lock, probe, timing), `problems/telemetry` (M7-reference problem and `batching` axis, earlier slices).

## Tests
Final full run (local, 2026-10-23, 18 min 56 s): `uv run pytest` **1,622 passed, 9 skipped, 0 failed**; `uv run ruff check src tests scripts` clean. New test files: `test_research_contract` (19), `test_campaign_knowledge` (7), `test_measure_worker` (10), `test_mission_lifecycle` (16), `test_evaluator_lock` (4), `test_domain_probe` (4), plus additions to `test_campaign_supervisor` (now 26), `test_m7_space`, `test_director_contract` and `test_research_program`. Not run: hosted CI, `fhel smoke`, any live Luna call.
