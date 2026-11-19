# Typed capability contract (WP1, WP2)

Module `src/fhel/research_contract.py` is the single declaration of what a research model may ask for.

| Derived artifact | From the contract | Status |
|---|---|---|
| Strict structured-output `params` schema | `params_schema()`, used by `model_route_codex.mission_output_schema` (identity asserted in `tests/test_research_contract.py`) | Implemented, locally tested. **Live strict-schema acceptance by the real Codex CLI is not yet tested** |
| Model-visible vocabulary | `vocabulary()` (shown under `lab.actions` in the Director context) | Implemented, locally tested |
| Admission of model proposals | `validate(category, params)`, wired in `mission_ops._wire_measure` for live (`codex-exec`) directors only; operator documents and the offline rule Director keep their existing paths | Implemented, locally tested |
| Worker-side validation | `measure_worker.normalize` (contract + domain membership), `research_worker.normalize_params` | Implemented, locally tested |
| Introspection | `vocabulary()` is JSON; `build_actions()` | Implemented |

Actions: `measure` (category `measure`), `explore` (category `experiment`, telemetry only), `code_research` (legacy, unchanged). A field is `enum | int | num | str | list | object`; lists and objects are bounded (`max_items`, total JSON <= 6000 chars, depth <= 3; task parameters accept structured values only for the allowlisted keys `configs` and `telemetry_space`). The M7 candidate axes (`batch_size`, `dictionary_kib`, `model`, `batching`) are generated from `problems.telemetry.DOMAINS`: adding an axis changes schema, vocabulary and validation together (test `test_a_new_domain_axis_appears_in_schema_vocabulary_and_validation_at_once`).

## Operational limits are not model-controlled (WP2)
`max_steps`, `per_experiment_max`, `max_experiments`, `study_deadline_seconds`, retries, timeouts and costs are not fields of any action; a live proposal that names one is refused by `validate`. Trusted derivation: `research_worker.normalize_params` derives per-experiment size, experiment count, step floor (6 integrity-v2 / 4 legacy) and deadline from the searched space; `measure_worker.plan`/`research_contract.measure_plan` derive evaluations (`2 x configs x repeats`: candidate + paired reference), repeats (trimmed first by remaining budget/time) and the worker wall limit; `DirectorPlanner.proposal_finalizer` overwrites the model's `cost_evals` with the trusted cost before admission. Operator-authored mission documents keep full explicit control of every knob.

## Not covered
Contract declarations exist for the M7 domain and the legacy code lab only; other domains (bin-packing, compression) are unchanged, outside the contract, and remain operational through the legacy path. Dataset requirements, scientific evidence requirements and expected outputs are described in prose in the action declaration (`cost`, `needs`, `produces`), not machine-checked. Status: **Not yet qualified** for new domains.
