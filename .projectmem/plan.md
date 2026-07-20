# MortrisClient — plan

> Editable **intent** file: ideas + plans — what we *mean to do*.
> This is NOT the event log. `events.jsonl` -> `summary.md` records what
> *happened*; this file records what we *intend*. The AI reads it at
> session start and edits it directly (like `PROJECT_MAP.md`): add ideas
> and plans, check items off, move done work down to Shipped. Plans are
> never logged as events.

## Ideas
- Build a game-agnostic Unity analytics SDK that owns offline persistence, batching, retries, delivery policy, diagnostics, and consent state.

## Active plans
- [x] Bootstrap the standalone Unity 6 analytics playground and keep its development-tool state out of Git.
- [x] U0: define and verify the UPM public API, validation contract, bounded handoff, fixtures, and sample.
- [x] U1: complete Android SQLite queue instrumentation, corruption recovery, and schema-upgrade tests.
- [x] U2: Android device delivery passed against `mortris-prod` and all controlled `mortris-sdk-test` retry, acknowledgement, and policy scenarios.
- [x] U3: Unity `6000.3.16f1` Android IL2CPP/managed-stripping build, custom Gradle-template dual ABI (ARMv7/ARM64) package proof, and API 25/35 device launches passed; project settings restored.
- [ ] Implement the self-hosted ingestion contract and integrate the package into a first game consumer later.

## Next
- U4: choose the first game consumer and map its semantic start/complete calls to the SDK for a measured parity comparison.

## Someday / maybe

## Shipped
_Move completed plans here so the top stays about the future._
