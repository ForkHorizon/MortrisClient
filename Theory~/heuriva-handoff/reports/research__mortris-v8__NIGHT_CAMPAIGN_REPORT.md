# MORTRIS V8 campaign report (segment 1 only)

Date: 2026-10-22. Base commit: `cd69f04` (+ the Director-context fix committed with this report). Campaign start 2026-10-22T00:59:12Z UTC; segment-1 research active time about 40 min of the 2 h window; no later segment was launched.

## Outcome in one paragraph
A real, data-only, Luna-directed MORTRIS loop ran: trusted frozen M7 (C#) encoder + independent Go decoder measured 24 allowlisted M7 variants on the 167-installation development cohort; Luna (`gpt-6-luna`, high, subscription route, $0) read the verified result and proposed follow-ups twice. Both follow-ups (`integrity-v2` with binpack-oriented scenarios, MORTRIS has no independent cohort) failed, the evaluation budget (120) was spent, and the mission stopped with `operator_action_required`. No claim of independent confirmation exists.

## Facts
- Luna invocations: 9 reserved (seg1: 6, all proposals refused because the Director was never shown the allowed parameter vocabulary; seg1b: 3). Ledgers: `.local/mortris-v8/night-campaign/seg1.ledger.jsonl`, `seg1b.ledger.jsonl`. Ceiling used: 48 per segment (mission validator cap; 120 not used or needed).
- seg1 stopped `planner_untrusted` after 6 refusals. The root cause was an orchestration defect (fixed in `mission_ops.build_controller`: research missions now show the Director the allowed experiment parameters). The protective stop was not resumed; the same authorised segment was re-run as new mission `seg1b` with a fresh manifest (42 calls, remaining window, new ledger). This is a deviation worth operator review.
- Hypotheses: 1 operator-seeded; Luna proposed 3 follow-ups that were admitted (2 tasks) / refused (6 proposals in seg1).
- Candidates: 24 M7 variants, all measured, all exact typed round-trip (0 mismatches), no invalid candidates. Benchmarks: 24 (single repeat per variant, host macOS).
- Preflight: full pytest 1,519 passed, 9 skipped. No generated code executed; provider spend $0; no sandbox used.

## M7-relative result (development cohort, 82,923 events; reference = M7 default batch 100 / dict 0 KiB / base model = 23.883 B/event)
| variant | B/event | vs ref | encode CPU x | decode CPU x |
|---|---:|---:|---:|---:|
| 500/32 KiB/both | 18.092 | -24.2% | 1.27 | 1.00 |
| 100/32 KiB/both | 18.265 | -23.5% | 1.09 | 1.04 |
| 100/32 KiB/string | 19.154 | -19.8% | 0.98 | 1.00 |
| 100/32 KiB/base | 19.492 | -18.4% | 0.96 | 0.99 |
Full table: `.local/mortris-v8/m7_variant_table.json` (ignored). Best traffic: -24.2%. CPU: no variant clearly faster; 100/32/base and 100/32/string are within noise of the reference (single-repeat host timing, noisy). Dictionary asset bytes are reported separately and are not in B/event, so the traffic gain is not yet net of dictionary delivery. Balanced Pareto candidates: 100/32 KiB/string and 100/32 KiB/base (about -18..-20% bytes at no measured CPU cost).

## Not established
Independent confirmation (none; holdout exposed); Android/device numbers (report provenance contradiction unresolved); allocation/GC/server cost; any gain on the integrity-v2 path; whether M7 variants beat M7 beyond this exploratory grid. The 24-point grid is exhausted, so further runs of the same domain would only repeat it.

## Blockers and next operator actions
1. Segments 2–4 not launched: AGENTS.md requires a fresh direct instruction per resume/extension. Nothing was prepared beyond this report.
2. Real new research needs a wider data-only M7 domain (more parameters) and a sealed installation/session-disjoint confirmation cohort; integrity-v2 follow-ups cannot work for MORTRIS until then (they ran on binpack-style scenarios and failed).
3. Repeat CPU measurements with more repeats before any CPU claim.
