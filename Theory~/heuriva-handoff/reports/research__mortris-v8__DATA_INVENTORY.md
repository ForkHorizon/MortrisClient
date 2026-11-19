# MORTRIS V8 local data inventory

Inventory date: 2026-10-21. Source root: local `MortrisV7Data/` handoff, assembled 2026-10-21. The 3.6 GiB tree contains 14,519 files. It is local-only and is now excluded from Git. Selected input identities and SHA-256 values are in the ignored `.local/mortris-v8/data_manifest.json`; the manifest deliberately excludes credential-like key and certificate files.

## Available evidence

| Input group | Local reference | What it contains | Evidence limits |
|---|---|---|---|
| Event exports | `experiments/night-run~/work/`, `snapshots/MORTRIS_handoff-v7~/data/`, `research/transport-v7/06-experiments/results/private/` | Multiple JSONL and gzip JSONL corpora, replay batches, and derived experiment inputs. | These are distinct snapshots. The handoff README reports 997,076 lines and 994,564 events for the main corpus, while a separate same-date snapshot has 991,633 lines. Reconcile before calculating new totals. Do not merge cohorts. |
| M7/V7 client | `source-snapshot/Runtime/Internal/Transport/` | C# event, column, identity, dictionary and frame implementation; runtime queue bridge; Unity tests and Android native artifacts. | A source snapshot, not the production project itself. Freeze its exact commit/hash before a new comparison. |
| Independent decoder/server | `snapshots/MORTRIS_handoff-v7~/server/internal/transportv7/` | Go frame/stream decoder and tests; accompanying server snapshot and database integration. | Decoder and server benchmark reports cover different workloads and boundaries. |
| Offline codec and replay experiments | `research/transport-v7/06-experiments/`, `experiments/night-run~/work/` | C#, Go, Python and native benchmark scripts, fixtures, logs and aggregate result files. | Historical results; do not treat scripts' existence as a fresh execution or as an independent confirmation. |
| Unity/Android | `research/transport-v7/06-unity-runtime-validation.md`, `experiments/night-run~/results/android/`, `experiments/night-run~/results/unity*` | IL2CPP and profiler summaries, emulator runs, plus a report section describing a Nothing A142 physical-phone run. | The night-run report contradicts itself: its opening scope says there was no physical device, while §8 reports phone measurements. Treat phone figures as reported, not independently verified, until raw run evidence is reconciled. |
| Server and transport | `experiments/night-run~/results/server*/`, `experiments/night-run~/results/firebase_wire/`, reports under `research/transport-v7/` | Go/PostgreSQL ingestion summaries and TLS test-receiver/request summaries for SDK comparisons. | No `.pcap`/`.pcapng` capture or Unity Profiler `.data`/trace file was found. Request bytes at the test receiver are not interface-level wire bytes. Phone connectivity was disabled during reported phone runs. |
| Competing SDK comparison | `research/transport-v7/comparison/`, `experiments/night-run~/results/` | Replayed event comparisons, emulator SDK requests, and delivery/CPU/memory summaries. | SDKs differ in event coverage, transformations, batching and delivery. Do not treat their samples as identical products. |

## Provenance and privacy

- The main night-run report identifies a 2026-10-20 export and 994,564 events across 217 installations; it describes 974,689 events in a selected V7 size analysis. The 2026-10-16 snapshot is separately reported as 524,934 events, 162 installations and 564 sessions. These counts come from existing reports and have not been recomputed here.
- Prior Heuriva M7 frame measurements used 74,559 sampled events from 152 development installations. The repository's exposure ledger says the historical validation/fresh and held-out cohorts were shown to a researcher; held-out is EXPOSED and cannot be reused as fresh confirmation.
- No per-row telemetry was copied into this repository. The complete handoff contains event payloads, build artifacts, logs, and credential-like key/certificate files. Those contents were not printed or committed. Only selected corpus, report and source checksums are recorded in ignored local storage.
- Dataset, source and runtime versions vary among the handoff subtrees. The private manifest records exact selected relative paths, sizes and hashes; it is not a substitute for a new dataset protocol or source audit.

### Export schema audit

The selected `night-run~/work/puzzle-1m.jsonl.gz` export has five fields outside the current Heuriva event-field list: `event_kind`, `effective_at`, `clock_skew_ms`, `time_quality`, and `sent_at_client`. Source inspection of the snapshot's Go ingestion contract and persistence path classifies them as follows:

| Field | Origin | Canonical event data? | Replay treatment |
|---|---|---:|---|
| `event_kind` | Server classification using project catalog state | No | Server-derived metadata, excluded from event frame |
| `effective_at` | Server clock-quality policy | No | Server-derived metadata, excluded from event frame |
| `clock_skew_ms` | Server receive time minus batch `sent_at_client` | No | Server-derived metadata, excluded from event frame |
| `time_quality` | Server clock-quality policy | No | Server-derived metadata, excluded from event frame |
| `sent_at_client` | Client batch envelope, copied onto each exported row | Not an event field; it is batch metadata | The current reconstruction substitutes a fixed timestamp and therefore does not reproduce the original batch envelope |

The event fields in the export agree with the strict client `contracts.Event` type. An aggregate check found one project value across all rows, matching the project assumed by the current reconstruction, and 34,834 distinct `sent_at_client` timestamps. This resolves the apparent five-field schema difference but does not make reconstructed bodies byte-identical: original request bodies/key order/numeric lexemes were not retained, and the current per-install replay resamples batch boundaries and substitutes a fixed timestamp. Report its byte counts as reconstructed V1 bodies, not original request bytes or captured traffic. The local schema audit is stored under ignored `.local/mortris-v8/schema_audit.json`; it contains counts and field names only, not event values or identifiers.

## Strongest available evidence

The strongest evidence is the existing frozen C# M7 encoder/independent Go decoder path, plus offline Unity/Android and Go/PostgreSQL report summaries. The Heuriva run is development-only and compares against reconstructed V1. The external handoff contains richer device/server measurements, but source reports disagree about device provenance and no fresh, installation-disjoint confirmation cohort is sealed. There is no captured interface-level network trace.
