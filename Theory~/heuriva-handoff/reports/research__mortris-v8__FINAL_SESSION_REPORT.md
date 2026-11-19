# MORTRIS V8 session report

Date: 2026-10-21. Outcome: **local research handoff prepared; trusted data-only M7 replay extended; CodeLab candidate execution remains gated.**

## Completed

- Read the supplied mission brief, current research roadmap, repository policy, MORTRIS runbooks/reports, exposure ledger, safety boundaries, and current M7/CodeLab entry points.
- Ran `uv run fhel status`: provider/evolution/execution modes are off, provider spend limit is $0, concurrency is 1, and the audit chain is valid.
- Verified the checkout is `wp-aut-04/autonomous-lab-reconstruction` at `1535b9f12bee9beb4693dc01323e889e89d9dd41`. The local `MortrisV7Data/` directory was untracked before protection was added; its contents were not modified.
- Added `MortrisV7Data/` to `.gitignore` because the 3.6 GiB handoff contains raw telemetry, build outputs and credential-like key/certificate files.
- Prepared the local-only input hash manifest and the inventory, research contract, baseline summary, experiment log, evidence frontier and continuation plan in this directory.
- Audited the selected export against the snapshot's strict client event contract and Go ingestion path. The four server-processing fields are documented as derived metadata; `sent_at_client` is batch-envelope metadata that the current replay cannot reconstruct. The telemetry loader now rejects missing or unmodeled fields and the evaluator identity moved from v5 to v6.
- Prevented the exposed MORTRIS validation/held-out cohorts from entering integrity validation: the verifier persists `no_independent_data` with a reason without loading either role, and the direct role API rejects both.
- Corrected CodeLab's statistical evidence labels. Protocol 3 describes the bootstrap fraction as a bootstrap summary, not a p-value; CodeLab no longer emits a p-value or reports independent confirmation from fixed-case timing repeats. The verifier rejects protocol-2 conclusions that still carry the old p-value claim.
- In a later bounded follow-up, fixed the M7 handoff resolver to support the repository's existing nested `MortrisV7Data/snapshots/MORTRIS_handoff-v7~` layout while preserving the legacy root path.
- Ran a new provider-`none`, data-only trusted M7 parameter sweep over 167 development installations (82,923 events), with 3 repeats and randomized pair order. Every emitted M7 frame passed Go semantic decoding; 300–1,500 events per configuration used M7 fallback. Summary values and evaluator/data hashes are under ignored `.local/mortris-v8/trusted_m7_full_dev_20261021.json`.

## Not completed

- No MORTRIS CodeLab domain or unified M7-referenced Android/network/server evaluator was implemented. Existing Heuriva M7 measurements still compare against reconstructed V1; batch boundaries and original envelope timestamps are absent from the selected export, so request-byte reproduction is not possible from that sample alone.
- No Luna call, generated candidate execution or integrated V8 benchmark was run. The trusted sweep is not the missing M7-referenced CodeLab evaluator: it compares fixed M7 configurations with reconstructed V1 on the same development cohort. Sandbox A1–A11 self-tests passed as implementer-run observations, but remain blocked pending independent review and acceptance evidence. The exposed historical holdout cannot serve as fresh confirmation. No unrelated synthetic-domain run was substituted.
- No new statistical claim, device result or improvement over M7 is established.
- Validation for this follow-up: `uv run pytest -q` (**1,519 passed, 9 skipped**); `uv run ruff check src scripts tests research`; `git diff --check`; `uv run fhel research selftest` passed A1–A11 as an implementer-run observation; the full trusted M7 replay sweep completed with all emitted M7 frames passing Go semantic decode. Hosted CI has not run on this follow-up.

## Strongest available result

Existing Heuriva evidence reports a development-only M7 frame payload of 16.926 B/event versus reconstructed V1 gzip at 118.824 B/event; all 14 measured rows passed its supported-field round trip. The new fixed-configuration sweep found 18.092–23.883 B/event versus reconstructed V1 at 119.133 B/event; every emitted M7 frame passed Go semantic decode, while M7 host encoding took longer. These are repeated development-cohort observations, not a candidate beating M7. Separate handoff reports contain richer V7 CPU, memory, Android, request and server measurements, but the phone provenance conflicts inside the report and the measurements are not integrated into the trusted Heuriva evaluator.

## Safety and next step

No provider calls or generated candidate executions occurred; provider spend remains zero. Trusted frozen M7/C# and Go replay code did run on the local development cohort. Raw telemetry and selected hashes remain under ignored local storage. Before a MORTRIS CodeLab candidate run, implement and qualify the M7-referenced CodeLab evaluator, obtain independent qualification for the execution tier, audit the device report provenance, and create a sealed installation/session-disjoint confirmation cohort. Any resumed or additional Luna segment also requires a new direct operator instruction. Do not launch the proposed night mission until its separate gates are satisfied.

## Git checkpoint

Engineering follow-up commit: `eb58ae9` (`fix research evidence and MORTRIS schema guards`) on local branch `daliys/mortris-v8-safety`. The earlier evidence handoff commit is `28cc0bf`. These commits have not been pushed and no PR has been opened; PR #22 was verified merged, and this follow-up has no hosted exact-head CI result.
