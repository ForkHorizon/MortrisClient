# Campaign-wide research memory (WP3)

`src/fhel/campaign_knowledge.py`: one append-only SQLite store (`<campaign>/knowledge.sqlite3`) shared by every mission round, segment and worker of a campaign; the supervisor injects its path into each round's mission document, so a new round starts with all prior evidence and nothing is re-seeded.

## Identity and deduplication
* **Context** = hash of (problem, evaluator id, reference candidate, dataset sha + role, measurement protocol). **Candidate** = family + canonical parameters. A measurement is "the same experiment" only if both match; a new evaluator, dataset, reference or protocol never inherits another context's "already measured".
* `unmeasured(ctx, cands, purpose)` returns (to_run, accidental_duplicates): purposes `replicate | investigate | compare` are intentional repeats and never duplicates; `explore` skips anything measured or previously failed. A failed candidate is recorded (rejection text) and is not silently retried.
* `record` is idempotent on (run, ctx, candidate, repeat): a resumed worker cannot duplicate a row; a resumed run finishes what it began (`measure_worker.run`).
* Admission (`measure_worker.admit`, `research_worker.unmeasured_space_check`) refuses a request whose entire content is already measured, at zero cost.

## What the Director sees (bounded, aggregates only)
`measure_worker.director_knowledge` -> `Knowledge.summary`: counts, Pareto frontier (<= 16 rows with n, means, sd, CPU verdicts, evidence level), best per objective, frontier members needing repeats, dominated count, failed candidates, per-axis measured counts, unmeasured count, domain-probe exclusions. The store holds no raw telemetry (only per-measurement aggregates), so private source data is inaccessible to the model by construction. Size is asserted < 12 kB for a 200-candidate store.

## Status
Implemented and locally tested (`tests/test_campaign_knowledge.py`, `tests/test_measure_worker.py`, real-data end-to-end runs in `ACCEPTANCE_REPORT.md`). Restart/segment survival: tested with real controllers (SIGKILL) and across missions on real data. Not live-tested with a model; not yet used for domains other than the M7 telemetry family. The legacy per-mission study database still exists for `explore`; its measurements are not imported into the store (only `measure` writes it), so `explore` results are invisible to knowledge-based dedupe except through the admission check that reads both (`unmeasured_space_check`).
