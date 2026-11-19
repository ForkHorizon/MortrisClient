# MORTRIS V8 research contract

Status: contract proposal only. No new MORTRIS evaluator or candidate execution was admitted in this session.

## Question and acceptance

Reduce end-to-end analytics cost while preserving every admitted event exactly. Correctness is a hard constraint: for the declared canonical schema, decoding the candidate output must reconstruct the exact input values, field presence/nullability, event order and identity semantics. Unsupported records must be rejected or routed through a declared lossless fallback and counted. Lossy transformations are out of scope.

The frozen M7/V7 implementation is the primary comparator. Reconstructed V1 gzip is a historical secondary reference. A candidate is not eligible for a Pareto comparison until it has a trusted evaluator, exact round-trip verification, and metrics for the same logical workload as M7.

## Metric contract

Report separate values, never one blended score:

1. Logical input bytes and eligible event count.
2. Encoded payload bytes, frame bytes (header, dictionary identity and CRC included), and fallback bytes.
3. Application request bytes at the instrumented endpoint, if captured; modeled transport overhead; interface/IP wire bytes only when an actual capture identifies that layer.
4. Client parse, construction, queue/batch, encode and flush CPU; allocations, peak memory and GC counts/duration when measured in the actual runtime.
5. Decoder CPU, allocations and peak memory; server ingestion and database CPU/RSS/storage as separate components.
6. Reliability: exact mismatch count, unsupported/fallback count, malformed-input rejection, delivered/duplicate/missing event counts, and retry/recovery behavior.

Every result names the runtime (Unity Mono/IL2CPP, Android device/emulator, .NET host, Go host), build mode, device, warmup, repetitions, clock/load controls, batch regime and raw evidence path. Host native measurements do not stand in for Unity managed allocations. A modeled byte count is not a captured network measurement.

## Cohorts and inference

- Development: exploration only.
- Selection: candidate ranking and tuning; not confirmation.
- Confirmation: new installation/session-disjoint data, frozen before candidate selection and never exposed to the researcher.

The existing telemetry holdout is EXPOSED. Until new confirmation is sealed, results remain descriptive/exploratory. Experimental units are installations or sessions, not repeated events. Pair candidate and baseline on the same workload; randomize order; report missing/rejected units and per-workload outcomes. Use bootstrap intervals as uncertainty summaries. Do not label a bootstrap exceedance fraction a p-value or claim formal significance without a valid hypothesis test and multiplicity procedure.

## Admission and safety

Only trusted, explicitly allowlisted evaluators and data-only `{family, params}` candidates may enter research under repository policy. Generated source is untrusted and cannot run under the current `AGENTS.md` gate. The user directly authorized one bounded Luna segment, but no call was admitted because the MORTRIS CodeLab evaluator is not qualified and generated-code sandbox acceptance remains blocked pending independent review. No paid API call was authorized or made. One active worker, finite caps, zero provider spend, immutable baseline, and no production deployment remain mandatory for any future run.

## Current capability gap

The current `event_codec` CodeLab domain is synthetic. The existing MORTRIS code path tests frozen M7 frames, but the recorded Heuriva comparison is against reconstructed V1 and does not integrate the external Android, request-capture and server metrics into one trusted M7-referenced evaluator. This session does not claim that the gap is implemented. The telemetry evaluator identity was intentionally versioned from 5 to 6 because its accepted export schema now fails closed on unmodeled/missing fields and its exposed historical roles are no longer admitted as independent validation. Existing telemetry studies pinned to version 5 cannot be resumed under the new identity.

The selected export contains server-derived `event_kind`, `effective_at`, `clock_skew_ms`, and `time_quality`; these are not fields in the client event contract and are excluded from client-frame replay. Its `sent_at_client` is batch-envelope metadata flattened onto exported rows. Existing replay reconstructs the envelope with a fixed timestamp and cannot recover original batch boundaries, so its payload sizes are not original request-byte measurements. See `DATA_INVENTORY.md` for the source audit.
