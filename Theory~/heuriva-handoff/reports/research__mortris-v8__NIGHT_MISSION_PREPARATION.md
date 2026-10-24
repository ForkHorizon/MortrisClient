# MORTRIS V8 night mission preparation

Status: **not launch-ready; do not start a night mission.**

## Qualified today

- Local Heuriva status is healthy and provider spend is configured to zero.
- Frozen M7 C# encoder plus Go decoder has a prior development-only Heuriva run with 14 successful measured rows and exact typed round trips.
- Local research inputs and selected hashes are preserved under `.local/mortris-v8/`; `MortrisV7Data/` is Git-ignored.

## Blocking gates

1. Resolve the repository `AGENTS.md` restriction. It explicitly limits authorized research to provider-`none`, data-only EXP02 and excludes external providers; it does not permit the attached Luna route.
2. Do not run generated code until the independent sandbox and protected evaluator gates pass under the current repository policy. The existing acceptance evidence is not promoted for this scope.
3. Build a trusted evaluator that uses the frozen M7 implementation as its reference on the same logical workload. Keep payload, frame, request, modeled network, and captured wire bytes distinct.
4. Reconcile the handoff report's contradictory physical-device statements by checking raw run provenance. Do not rely on emulator numbers as physical-device evidence.
5. Freeze a fresh, installation/session-disjoint confirmation cohort before selecting candidates. The historical telemetry holdout is exposed.
6. Integrate correctness/fallback accounting and paired CPU, allocation, GC, memory, decoder and server metrics; set per-workload caps and persist raw evidence privately.
7. Review the exact Git branch, active PR and exact-head CI before any milestone update or push. Do not merge to main under this brief.

## Safe local recovery

The completed historical M7 Study is under `.local/telemetry-research/mortris-v7-frame-verifier-recovery-20261020/`; it is evidence to inspect, not a resume target. Start a future authorized session with:

```sh
cd /Users/daliys/Daliys/AI_Test_PlayGround/Heuriva
uv run fhel status
git status --short --branch
```

Do not resume or extend a live mission automatically. Once all blockers are cleared, prepare a new finite manifest and mission from the current checked-in schemas; never reuse an expired manifest or the exposed confirmation data.
