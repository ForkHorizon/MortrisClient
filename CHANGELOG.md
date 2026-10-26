# Changelog

## 0.2.0 - Unreleased

- Started the 0.2.0 development line on `develop`.
- V7 transport (opt-in `AnalyticsOptions.UseTransportV7`): native zstd plugin (arm64-v8a, armeabi-v7a, macOS Editor), C# M7 encoder,
  sequence streams with acknowledgement by sequence, asset/alias handling and automatic V1 fallback. See `Documentation/V7Transport.md`.
- Event pipeline rewrite: events are written once as binary records and buffered in memory (`AnalyticsOptions.EventBufferWindow`, 200 ms); the Android
  queue (schema v4) stores them as blobs in one transaction per window and keeps its counters in memory; transport V7 and V1 both read the records, so no
  JSON is built or parsed on the way. Rows queued by older versions are migrated. See `Documentation/EventPipelineAndSessions.md`.
- Sessions: the SDK now observes pause/focus/quit, emits `sys_session_start`, `sys_app_background`, `sys_app_foreground` and `sys_session_end`, writes buffered
  events before the game is suspended, and closes the session of a process that died (Android exit reason). New options `EventBufferWindow` and
  `SessionTimeout`. Projects using V7 need the four lifecycle shapes in their catalog.
- V8 transport (opt-in `AnalyticsOptions.UseTransportV8`, `Documentation/V8Transport.md`): server-issued short installation id and token, shapes learned by the SDK and
  registered in the packet that first uses them, first packet of a normal launch without a handshake, minimal acknowledgement, server-trained dictionary. Numbers keep
  their type in event records (`float` stays float32). `Analytics.NextId(counter)` hands out numbers that survive a crash together with the events that used them.
  The Android queue gained a small key/value store (`v8.*`, `counters`), counters in the batch transaction and `adoptIdentity`.
- Upload schedule (see `Theory~/transport-v8/PROTOCOL.md`, D13): default `UploadInterval` 120 s (was 30 s), `UploadEventThreshold` 200 (was 50), new
  `MaxPacketEvents` (200), `UploadOnBackground`, `BackgroundUploadMinGap`, `BackgroundUploadTimeout`; one short upload attempt when the game goes to the
  background or quits. New `MaxEventsPerSecondPerName` and `Analytics.SetEventRateLimit` for event floods.
- Android queue schema v3: a durable journal of locally dropped sequence ranges (evicted, expired, or cleared
  events), a `stream_base` marker, and `AnalyticsQueue.getSequenceState()`. Foundation for the V7 sequence-identity
  delivery contract; the wire format and server contract are unchanged.


## 0.1.4 - Unreleased

- Added human and AI integration guides with lifecycle, consent, event-schema,
  diagnostics, and Android validation guidance.
- Renamed the server-reported SDK identity to `mortris-unity` and aligned its
  version with the package release.
- Added direct documentation and changelog links to the package manifest.

## 0.1.3 - 2026-07-21

- Added **Fork Horizon** as the Unity Package Manager package author.

## 0.1.2 - 2026-07-21

- Renamed the visible package and README title to **Mortris Analytics**.

## 0.1.1 - 2026-07-21

- Removed the tracked Graphify marker that caused Unity to warn about a
  metadata file inside an immutable Git package.

## 0.1.0 - 2026-07-20

- Added the public Unity API, event validation, diagnostics, and sample.
- Added the Java 11 Android SQLite queue, JNI persistence bridge, durable
  batching, gzip uploader, retry/policy handling, and Android device proof.
