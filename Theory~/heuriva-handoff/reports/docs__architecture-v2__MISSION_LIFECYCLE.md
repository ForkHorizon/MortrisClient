# Mission lifecycle (WP6)

## Typed contract
`src/fhel/mission_lifecycle.py`: `StopKind` (running, waiting_for_resources, recoverable_failure, scientific_task_completed, task_failed, program_coverage_achieved, scientific_question_answered, research_opportunities_exhausted, authorization_expired, budget_exhausted, safety_stop, integrity_failure, operator_action_required) and `Disposition` (recover, continue, finish, limited_continue, hard_stop). `classify(stop, tasks, controller_alive)` maps every controller stop reason (test: all `_stop("...")` literals of `mission_continuity` are classified) and **fails closed** on anything unknown (`integrity_failure`/`hard_stop`). `operator_action_required` is refined by task state: only FAILED/stranded tasks -> `task_failed`/`continue`; `NEEDS_APPROVAL`, `OUTCOME_UNKNOWN`, `BLOCKED` -> hard stop.

## Routine failures
`MissionSpec.routine_failures` (document key `routine_failures`, omitted from the digest when false, so historical digests are unchanged): a FAILED task is a recorded outcome, not a human gate. Human gates and safety stops are unaffected (tested).

## Slot / round / mission
* **Slot** = the authorised window + call ceiling (a segment of the campaign authorization). **Round** = one mission inside a slot. The research objective continues across rounds: when a round ends in an ordinary way, the supervisor starts another round in the same slot while >= 600 s, >= 3 calls and admissible work remain; rounds share the campaign knowledge store and begin with a *free briefing task* (no seed study). A slot ends on window/call exhaustion, no admissible work, or two consecutive rounds without new persisted measurements; two consecutive stagnant slots end the campaign as `research_opportunities_exhausted` (an honest early conclusion, not padding).
* Invocation accounting is cumulative over **all** ledgers of the campaign (`spent_total`), per slot over its rounds (`slot_spent`); each round's route manifest is clipped to the remaining slot calls, total calls and absolute deadline.
* Hard stops stay immediate: unknown reason, safety/integrity, operator gate, login/quota, recovery budget, evaluator drift, deadline.

## Honest limitation
A route manifest binds one mission, so mission *identity* is not literally continuous across rounds; continuity is provided by the shared store and the briefing, not by one long mission. Status: implemented + locally tested with stub and real controllers (see `ACCEPTANCE_REPORT.md`); not live-tested with a model.
