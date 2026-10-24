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
