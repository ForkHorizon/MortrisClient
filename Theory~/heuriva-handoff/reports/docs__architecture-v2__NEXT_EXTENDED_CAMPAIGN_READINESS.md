# Next extended campaign — readiness and launch procedure

Status: **`READY_FOR_BOUNDED_LIVE_CANARY`** (not `READY_FOR_EXTENDED_CAMPAIGN`). Evidence: `ARCHITECTURE_RECOVERY_REPORT_2026-10-24.md`. This document does not authorize anything; no authorization document or digest exists for the next campaign, and none of the 2026-10-23/24 digests may be reused (all are ended or closed).

## 1. What is qualified

| Item | State |
|---|---|
| Qualified commit | `f795857b2337074fc674d80aeb9f934586b0829f` (code; later commits are documentation only) on `daliys/fix-over-limit-stop` (PR #25, draft). Use the commit that is on `main` once the PR is merged; do not run from an unmerged working tree |
| Evaluator | `telemetry_m7_payload`, sha256 `33980c0c0526c9abb438c8f82b243c97bbf28a2357a88e42e6bb890946f54698`; frozen reference = M7 default (batch 100, dict 0 KiB, base, fixed); the supervisor writes `evaluator_lock/` and stops on drift |
| Dataset | `MortrisV7Data/experiments/night-run~/work/puzzle-1m.jsonl.gz`, sha256 `8475bd3d37b007576371548518793e0ffa7c85821557c1a967b309e54a656ca3` (development cohort; holdout exposed; no confirmation cohort) |
| Research capabilities | `measure` (exact configs, paired repeats, replication cap 15 rows/candidate), `explore` (legacy search, mostly-known spaces refused); **no** generated-code execution, no new candidate family. Domain: 168 M7 configurations, all covered once; 105 paired-measured |
| Template | `research/mortris-v8/campaign_template_v5.json`. v3/v4 are refused by `make-auth` (infeasible mandatory goal) |
| Model route | `gpt-6-luna`, effort high, `codex-exec`, subscription login. The **flat** decision shape with per-category proposal variants was accepted by the real route in 412 calls on 2026-10-24 (earlier code). **Not yet run against the real route:** the current Director context (`admissible_now`, `recent_refusals`, `replication_cap`), the changed prompt text, and the `union` decision shape (off) |

## 2. Authorizing one campaign

1. Decide first whether this campaign belongs to an existing **group** (related campaigns share one ceiling). Default group = `<operator>-<UTC date>` with a 480-call ceiling; a larger ceiling must be passed with `--group-ceiling` and becomes part of the digest you approve.
2. Create the document **at launch time** (its `start_epoch` is fixed to now + `--start-in-minutes`, the deadline is start + hours; a document made early wastes the window):
   ```sh
   uv run python -m fhel.campaign_supervisor make-auth --dir .local/mortris-v8/<new-dir> --campaign-id <new-id> --operator daliys \
     --hours 8 --total-invocations 480 --start-in-minutes 3 --dataset "MortrisV7Data/experiments/night-run~/work/puzzle-1m.jsonl.gz" \
     --mission-template research/mortris-v8/campaign_template_v5.json
   ```
   It refuses an infeasible template or a request above the group's remaining allowance, and prints `approve_digest`. Read `authorization.json` (segments, ceilings, group) before approving.
3. Approve = pass that digest to `run`. Only the operator does this; nothing in chat creates budget.
4. Optional canary first: a separate small authorization (`--hours 0.5 --total-invocations 3`, same group) running the same template; check the first Director decisions and the ledger (§6) before authorizing the long one.

## 3. Starting

```sh
export FHEL_TELEMETRY_DATASET="$PWD/MortrisV7Data/experiments/night-run~/work/puzzle-1m.jsonl.gz"
caffeinate -i nohup uv run python -m fhel.campaign_supervisor run --dir .local/mortris-v8/<new-dir> --approve-digest <digest> --assess-seconds 1200 > .local/mortris-v8/<new-dir>/supervisor.out 2>&1 &
```
Preflight (all must hold): clean `git status` on the qualified commit; hosted CI green on that commit; `codex login status` = ChatGPT; dataset present; `uv run fhel status` healthy; full `pytest` and ruff pass; no other supervisor/controller running (`ps`); knowledge to carry over (if any) copied from a **closed** campaign directory and re-ingested, never from a running one.

## 4. How calls and time are accounted

- One authorization = one campaign. Calls are counted from every `<slot>[rN].ledger.jsonl` (reserved calls, unknown outcomes included, never refunded) and the group registry (`.local/mortris-v8/campaign_groups/<group>.jsonl`). A restart reads the same ledgers, so it cannot reset usage. The deadline is a UTC epoch; DST does not matter. Monotonic and launch clocks are reported next to it.
- The 480 calls are a ceiling, not a target. Segments (slots) have up to 48 calls and their own window; a **slot** running out of calls or time is `slot_complete` and the campaign continues with the next slot. Only campaign-wide budget/time, an exhausted domain, a verified answer or a hard stop end the campaign. **Mission rounds** are missions inside a slot; they share the knowledge store.

## 5. Failure behaviour

| Situation | Behaviour |
|---|---|
| controller or worker crash | recovery per the authorization (≤2 per incident, ≤5 total), same round, state preserved; ledger shows each reserved call once |
| supervisor killed / Mac restarts | run the **same command** again: lock, state, rounds and verdicts are reloaded; the deadline does not move. `SIGTERM`/`SIGINT` is a clean pause (no outcome) |
| model timeout | one typed timeout is retried (bounded); other typed failures end the round or stop per kind |
| input too large / output contract | round ends (`CONTINUE`); context is bounded below the route limit before every call |
| auth / quota / budget exhausted | hard stop (`quota_or_auth_error`, `invocation_budget_exhausted`) with state preserved |
| scientific domain exhausted | `domain_exhausted`; two slots without new information → `research_opportunities_exhausted` |
| mandatory goal impossible | refused at `make-auth`; at runtime `program_unsatisfiable` |
| repeated Director refusals | feedback is carried across rounds; state-based refusals are bounded separately; two trust-limit rounds in a row hard-stop |
| abandoning a paused campaign | `uv run python -m fhel.campaign_supervisor close --dir <dir> --reason "<why>"` (refuses while a controller is alive); a closed or ended campaign never restarts |

## 6. Monitoring and reporting

Every 1200 s an assessment (`assessments/NNN.json`) with `health`, `progress`, typed route errors, counters and a named `verdict`; heartbeats every ~45 s; `timing_breakdown.json` and `finalization/{facts.json,FACT_SKELETON.md}` rewritten at each assessment and at the end (also after a hard stop). The skeleton marks all analysis as PENDING; the narrative reports are written afterwards from those facts (`uv run python -m fhel.campaign_facts <dir> --write` regenerates them).

Canary checklist (first 1–3 decisions): the real route accepts the schema; no `kind=` route error; the Director's rationale mentions the cap/refusals correctly; no empty `propose`; ledger `input_bytes` below the cap.

## 7. Hard stops (cannot be bypassed)

Invalid authorization or digest; deadline; invocation ceiling (campaign or group); login/quota/auth failure; evaluator or dataset integrity; unsafe termination; unknown stop reason; recovery budget exhausted; repeated untrusted planner; concurrency violation; an ended/closed campaign; an unregistered group directory.

## 8. Operator actions that remain

1. Review and merge PR #25 (the working tree must run the qualified commit).
2. Decide whether the 1–3 call canary is wanted (recommended) and approve its digest.
3. Create the real authorization at launch time and approve its digest.
4. Afterwards: read `finalization/` and the assessments; decide about resuming, closing or a new campaign.

## 9. Known limits of this readiness

The scientific value of another M7 run is low: the finite domain is covered and the best-balanced candidate is repeated (see `OVERNIGHT_RESEARCH_RECONCILIATION_2026-10-24.md`). A long run only makes sense after a new trusted candidate family, a sealed confirmation cohort or additional measured dimensions (dictionary delivery, framing bytes) exist.
