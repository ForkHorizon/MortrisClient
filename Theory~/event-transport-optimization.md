# Mortris Analytics: minimizing event traffic (transport V2 theory)

Status: **theory / proposal, nothing here is implemented.** Written on branch `develop` (SDK 0.2.0) from a design
discussion with another AI plus a read of the 0.1.4 code. This file is meant to be handed to an AI **without the
codebase**, so it includes a self-contained description of the current system (section 2) and marks what is verified
against code versus what is a claim from the discussion.

Confidence tags used below: **[code]** verified in this repo, **[report]** stated in the game's
`analytics-events.md` report (not in this repo, not re-verified), **[experiment]** from a synthetic experiment of the
other AI (not reproducible from this repo), **[theory]** proposal/opinion.

## 1. Goal

Deliver the same logical event history with the fewest bytes, requests and battery, **without losing data or accuracy**.
The metric that matters is the **final compressed HTTP request body per event**, not the size of in-memory objects.
JSON key names compress extremely well under gzip, so removing repeated keys saves much less on the wire than it
appears to on paper.

Non-goals: promising a fixed saving (the honest claim is "tens of percent", not 90%); inventing a custom bit protocol
before benchmarking existing formats; collecting more personal data just because bytes are cheap (see section 11).

## 2. Current system (SDK 0.1.4, as of `main`) [code unless noted]

Package `com.daliys.analytics` ("Mortris Analytics", Unity UPM package, author Fork Horizon). Repo layout:

- `Runtime/Analytics.cs` public API (`Analytics.Track(name, properties)`), `Runtime/Internal/AnalyticsRuntime.cs`
  creates events (`event_id` = `Guid.NewGuid()` text, `session_id` = one GUID per runtime, `session_elapsed_ms` from a
  stopwatch, `occurred_at_client` UTC timestamp).
- `Runtime/Internal/EventValidator.cs` limits: event name and property keys snake_case, name <= 64 chars, key <= 64 B,
  <= 32 properties, value <= 1024 B, all properties <= 8 KB.
- `Runtime/Internal/PersistenceEventSerializer.cs` serializes each event to JSON **with the device context repeated in
  every event**: `event_id, session_id, name, occurred_at_client, session_elapsed_ms, app_version, build_number,
  platform, os_version, device_class, locale, timezone_offset_minutes, properties{...}`.
- `Runtime/Internal/AndroidQueueBridge.cs` + `Native~/android/analytics/.../AnalyticsQueue.java`: durable SQLite queue
  on Android. Table `pending_events(row_id, event_id UNIQUE, install_id, session_id, sequence, session_elapsed_ms,
  name, occurred_at_client, properties_json, properties_bytes, payload_json, created_at_epoch_ms, attempt_count)`.
  **A per-install monotonic `sequence` already exists** (persisted counter `next_sequence` in `metadata`, also copied
  into `payload_json`). Methods: `enqueueBatch`, `readOldestBatch(maxEvents)`, `deleteAcknowledged(eventIdsJson)`,
  `clearAllPendingEvents`, `resetIdentity`. The queue stores the **ready-to-send JSON** (`payload_json`).
- `Runtime/Internal/AnalyticsUploader.cs`: max batch 100 events; options default `UploadInterval` 30 s,
  `UploadEventThreshold` 50, `DurableEventLimit` 10000, `DurableByteLimit` 20 MB, `MaxEventAge` 7 days
  (`AnalyticsOptions.cs`). Endpoints: `POST /v1/installs/register`, `POST /v1/client/policy`,
  `POST /v1/events/batch`. Batch body (JSON, gzip, `Content-Encoding: gzip`, `Authorization: Bearer <installation
  credential>`):
  `{"schema_version":1,"project_id","install_id","sdk":{"name","version"},"sent_at_client","events":[...]}`.
  Response: `accepted[]` and `duplicates[]` (event_id lists), `rejected[{event_id,code}]`, plus `server_time` and
  `client_policy{mode: Active|PauseUpload|DisableCollection, next_check_seconds, discard_pending}`. Acknowledged ids are
  deleted from SQLite; everything else stays queued. Backoff 5 s up to 5 min. All of this is JSON via `JsonUtility`.
- Server-side policy can pause upload or disable collection. Android is the only persisted/uploading platform in 0.1.4.

Facts from the game report [report]: batches of 50 representative events; about **1096 B per event as plain JSON and
about 170 B after gzip (84.5% already removed)**; these are estimates for representative batches, not measured network
traffic. Event mix in one test snapshot: `state_checkpoint` 21.93%, `detail_taken` 21.90%, `detail_released` 21.89%,
`placement_resolved` 21.89% (together about 87.6%; one snapshot, not production statistics). Observed redundancy:
`attempt_id` and `wave_attempt_id` carry the same UUID; `app_version` appears both as an SDK system field and inside
`properties`; some fields change only per attempt, not per event; `placed_state_hash` is a 64-char hex SHA-256 string.

Game-specific names (`attempt_id`, `house`, `wave`, `block_id`, `placement_resolved`, ...) belong to the integrating
game (a puzzle game), not to the SDK. The SDK only sees a name plus a property dictionary.

## 3. Key insight

Do not just "compress JSON better". Build a **schema-aware, context-aware, delta-encoded transport**: both sides know
the event structure in advance, so the wire carries mostly changed values. Internally (game side, server side,
analytics DB) data stays human-readable with real names; only the network representation is compact. The durable
local queue must stay independent of how events are later packed for sending (so a crash never loses unsent
interactions, and a V1 queue can still be sent by a V2 client).

## 4. Optimizations, ordered roughly by risk/benefit

### 4.1 Remove duplication (P1, lowest risk) [theory]
Drop duplicated fields (`wave_attempt_id` == `attempt_id`, `app_version` in both SDK fields and `properties`). This
needs no new format and helps even with plain JSON+gzip. Fields that change only per attempt move to context (4.2).

### 4.2 Context hoisting with a context table (P1)
Same idea as OpenTelemetry resource attributes. Four layers:

| Layer | Frequency | Content |
|---|---|---|
| Batch header | once per batch | protocol version, schema id/fingerprint, install id, base timestamp |
| Session context | per session | app version, platform, device, locale, session id |
| Gameplay context | when it changes | attempt id, house, city, wave, progress state |
| Events | each | type id, time delta, changed fields only |

**Pitfall:** one batch can contain several attempts or even several sessions (offline accumulation, 7-day retention,
100-event batches). Never apply the first event's context to the whole batch. Ship a **context table** in the batch and
give each event a small `context_id` pointing into it. Today the device fields (`app_version`, `os_version`,
`locale`, `timezone_offset_minutes`) are written per event at serialization time from the *current* device context;
when moving to hoisting, decide whether the context must be captured at enqueue time (an event queued before an app
update and sent after it must keep its original `app_version`).

### 4.3 Numeric ids instead of names (P2)
Map `placement_resolved -> 21`, `block_id -> 4`, `outcome -> 8` etc. Developers keep calling
`Analytics.Track("placement_resolved", props)`; the SDK/schema compiler maps names to ids, the server reverses it.
Small ints cost 1 byte in varint encodings (Protobuf).

- Prefer the schema **baked into the SDK/game build** (generated at dev time). The client sends only a `schema_id` /
  fingerprint; the server checks it knows it, otherwise uses a fallback path. Do **not** make the server push the
  full dictionary every session (it would spend traffic to save traffic). Dynamic schemas are allowed: the server
  sends the dictionary once and the client caches it.
- Unknown event/field: send the original name with typed values (fallback), switch to numeric ids after the new
  schema version is registered.
- **Never reuse a numeric id with a different meaning** (same rule as Protobuf field numbers). Old events sitting in the
  queue must not be decoded with a dictionary from a newer build.
- Today's validator constrains names to snake_case and properties to 32 keys; a schema registry must stay compatible
  with that or define the transition.

### 4.4 Delta encoding (P3)
Send one base timestamp, then per-event deltas (`0, +150, +130, +130 ms`), optionally delta-of-delta. Same for
counters (`placed_block_count` as `+1`), coordinates, etc. **Not every field is safely reconstructible:**
`session_elapsed_ms` may include pauses while `active_elapsed_ms` excludes them, so one must not be derived from the
other. Perfetto combines interning, default values and deltas (reference for this style).

### 4.5 Binary ids and hashes (P3)
UUID text is 36 B, binary 16 B (saving is smaller after gzip). Better: replace per-event random UUID `event_id` with
`install_id` (sent once) + monotonic `sequence`; the server dedups on `(install_id, sequence)`. **This is cheap here
because `AnalyticsQueue` already persists a per-install `sequence`.** Requirements: the counter must never be reused
after a crash, data clear, queue restore or `resetIdentity`. The batch response can then acknowledge **ranges** of
sequences plus an explicit exception list instead of echoing up to 100 UUIDs (also cuts downlink bytes). A 64-char hex
SHA-256 (`placed_state_hash`) is 32 B binary, and can be omitted entirely when the server can reconstruct that state.

### 4.6 Game-specific: interaction frames and state deltas (P4, probably the biggest win)
Four event types are ~87.6% of the sample [report]. One player action produces a chain of related events
(`detail_taken`, `detail_released`, `placement_resolved`, `state_checkpoint`). Idea: the client emits one compact
**interaction frame** with timestamps of all intermediate steps; the server expands it back into the original logical
events, so the analytics DB barely changes. `state_checkpoint` after a successful placement is largely redundant with
`placement_resolved`: encode checkpoints as **deltas from the previous state** with periodic full snapshots (like video
keyframes). Do not drop checkpoints, keep full history. Risk: unfinished interactions at app kill; packing must happen
at send time, never replace durable per-event storage.

### 4.7 Format and compression (P3/P5)
| Option | Pros | Verdict |
|---|---|---|
| Protobuf | types, numeric field numbers, varint, ZigZag, unknown-field skipping, schema evolution | main candidate |
| MessagePack / CBOR | flexible, easy to adopt | reasonable intermediate step |
| Custom bit protocol | max control | only after benchmarks (maintenance cost for a few bytes) |

Compare `gzip` vs `Brotli` vs `Zstandard`. Zstd with a **pre-shared trained dictionary** (known to both sides, never
transmitted) can help small similar messages a lot; its CPU/battery cost must be measured. MessagePack is not
guaranteed to beat gzip-compressed JSON, always compare final compressed size.

### 4.8 Batching strategy (P5)
Fewer radio wake-ups matter more than a few bytes (Android guidance: batch, avoid frequent radio activation). Instead
of fixed `50 events / 30 s`, choose batch size adaptively from queued count, compressed size, network type and
app-background transitions. Larger batches are not always better; depends on play-session length and fill rate. Note the
current hard cap of 100 events per batch in `AnalyticsUploader`.

## 5. Possible shape of "Mortris Batch V2" (conceptual, binary on the wire) [theory]

```
HEADER         protocol=2 schema=7 install=<uuid> base_time=...
SHARED CONTEXT app=1.1.14 platform=android session=...
CONTEXT TABLE  ctx[0] = attempt:12 house:4 wave:3 ...
EVENT RECORDS  [type=21, dt=+150, ctx=0, {4:7, 8:1}]
               [type=22, dt=+130, ctx=0, {4:8, 8:2}]
```
Server decodes to ordinary named objects, then runs the existing validation and writes to the analytics DB. V1 and V2
must coexist: the SDK keeps supporting both; negotiate via `schema_version`/capabilities in the register/policy
exchange; if the schema or encoding is unknown, fall back to V1 instead of dropping events. Format versioning is
independent of game-content versions.

## 6. Experiment results [experiment, treat as indicative only]

3000 synthetic events, batches of 50, structure similar to the game's. Compressed body per event:

| Variant | Bytes/event | vs baseline |
|---|---|---|
| Current JSON + gzip | 99.5 | baseline |
| Shared context + JSON + gzip | 91.6 | -8% |
| Compact MessagePack + gzip | 65.2 | -34.5% |
| Compact MessagePack + Brotli | 60.6 | -39.1% |

The compact variants bundled several optimizations (numeric codes, contexts, binary UUIDs, time deltas), so this does
not isolate MessagePack. The 99.5 B baseline does not match the report's 150-180 B because synthetic data is more
repetitive: **do not trust any ratio until measured on real data.** What it supports: hoisting helps even on top of
gzip, and combined structural optimization beats renaming strings.

## 7. Correctness and safety constraints

- V1 vs V2 equivalence test: the same logical event stream must decode to equivalent records (except agreed id-format
  changes). This is mandatory before shipping.
- Persistence stays event-by-event and format-agnostic; packing happens at upload.
- Idempotency: server dedup must survive retries and partial acceptance; keep `accepted / duplicates / rejected`
  semantics (or their range-based equivalent).
- Old queued events are decoded with the schema they were written under.
- Privacy: this is an SDK possibly distributed in the EU. Keep purpose limitation, consent where required, data
  deletion, and no unnecessary device-data collection (EDPB / Android guidance on analytics SDKs). Smaller payloads must
  not become a reason to collect more.

## 8. Roadmap

| Pri | Task | Result |
|---|---|---|
| P0 | Capture real HTTP payloads from the game (500-5000 consecutive events with original batch boundaries) | trustworthy baseline |
| P1 | Remove duplicates; shared + gameplay context with context table | small-risk first savings |
| P2 | Schema registry and numeric ids | compact + versioned format |
| P3 | Protobuf, time deltas, binary ids / sequence-based dedup | main transport gain |
| P4 | Interaction frames and state-delta checkpoints | optimize the dominant events |
| P5 | gzip vs Brotli vs Zstd(+dictionary), adaptive batching | best size/CPU/battery tradeoff |
| P6 | V1/V2 equivalence on identical streams | no-loss guarantee |

## 9. Open questions

- Real production event mix and batch fill pattern (only one test snapshot exists).
- Does context have to be frozen at enqueue time (see 4.2) given retention up to 7 days?
- Does the server (not in this repo) already support non-JSON bodies, or only `application/json` + gzip?
- Is `queued payload_json` (pre-serialized in SQLite) acceptable for V2, or should the queue store structured columns so
  hoisting/deltas can be computed at send time? (Today the queue holds ready JSON, which makes batch-level
  hoisting awkward.)
- How is `placed_state_hash` defined and can the server reconstruct state to omit it?
- Which clients matter: only Android is persisted/uploaded in 0.1.4.
