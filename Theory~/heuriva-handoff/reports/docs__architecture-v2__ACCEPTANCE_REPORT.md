# Architecture v2 - acceptance report (offline, real MORTRIS fixtures, no model calls)

Date 2026-10-23, branch `daliys/architecture-v2`. All runs: provider none, deterministic rule Director (no Luna), real controllers and workers, real M7 C# encoder + independent Go decoder, development cohort (167 installations, first 600 events each), one host (macOS, Apple Silicon). Evidence is under ignored `.local/mortris-v8/arch-v2/`. **Nothing here is a live test and nothing is a scientific result.**

## A. Same task, old path vs new path (`bench/`)
Task: measure the same 8 M7 configurations (batch 25/50, dict 16 KiB, model base/integer, batching fixed/session) against the frozen M7 default.
| | old: `explore` study (campaign + planner) | new: `measure` (direct, paired) |
|---|---|---|
| wall, first run | 213 s | 117 s |
| wall, repeat on a quiet machine | 263 s | 133 s |
| ratio | | 1.8x and 2.0x faster |
| M7 measurements made | 8 (+ reference handling inside the campaign) | 16 (every candidate with its own adjacent reference) |
| evidence produced | best/dev-gain scalars | per-candidate paired bytes + encode/decode ratios, uncertainty-capable rows in the knowledge store |
Caveats: one run per arm per condition, the first old run overlapped my own test runs (hence the repeat); the new path does more M7 work and is still faster because it has no campaign/planner machinery; absolute times vary with host load (both arms were slower in the second run).

## B. Four-task mission on real data (`mission_b`): dedupe across missions and replication
`brief` (free briefing) 5.2 s, 0 evaluations; `dup` (2 configs already measured by an earlier mission) **0 admitted, 2 skipped, 0 s of measurement**; `new` (1 config, 2 repeats) 28.3 s execution = 4 M7 measurements (7.1 s each); `rep` (deliberate replicate of a measured config, 2 repeats) 27.6 s. Whole mission 81 s. Rows persisted in the shared store; a worker killed mid-run (first mission, SIGINT/pause) left 3 stored pairs and no duplicates.

## C. Supervisor lifecycle, 2 slots (`acc/run1`): `scripts/unattended_acceptance_v2.py`
Evaluator lock written, domain probe run once (6 probes, 0 exclusions), SIGKILL of the controller at 150 s -> detected, resumed once (5 s backoff); two slots, one mission round each, both ended `finalization_reserve` (mission window) and were classified `authorization_expired/continue`; outcome `all_authorized_segments_completed`; exit 0; no interactive input. 1186 s total.
| metric | v2 offline run | previous real 4 h campaign (Luna) |
|---|---|---|
| unique / total measurements | **72 / 72 (100%)**, 0 duplicate rows | 102 / 157 (65%) |
| wall in seed/initialisation work | 74.2 s worker init (6% of 1183 s) + 2 free briefings | 3028 s of 4950 s in seed studies (61%) |
| wall in actual experiment execution | 1080 s (91%) | not separated |
| controller overhead / idle / recovery wait | 0.7 s / 3.5 s / 5 s | not recorded |
| model decision time | 0 (no model) | 398 s for 26 calls (8%) |
| failed studies from bad limits | 0 (limits not model-controlled) | 4 of 20 |
| throughput | 72 unique configs in 1183 s = 16.4 s/config | 102 unique configs in 4950 s = 48.5 s/config (includes model calls and seed studies) |
Not comparable like-for-like: the old figure includes Luna latency and seed studies by design; the new run has no model. The point demonstrated is where time goes, not a speed claim about a future Luna campaign.

## D. Not demonstrated
* 30-minute assessment interval (the run lasted 19.8 min; the interval was exercised in the earlier v1 run, 1806 s) and a second round inside one slot (slots ended with < 600 s left; round logic is covered by stub-controller tests only).
* Provider interruption, quota/auth failure, rejected live proposal, live strict-schema acceptance, any Luna interaction with `measure`.
* Legacy domains were only exercised by the existing test suite (bin-packing and compression studies, code lab) - see the test counts in `IMPLEMENTATION_STATUS.md`.

## E. Tests
Full suite 1,622 passed / 9 skipped / 0 failed; ruff clean (details in `IMPLEMENTATION_STATUS.md`).
