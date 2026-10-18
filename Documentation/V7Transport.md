# V7 transport (opt-in)

V7 sends events as compact binary packets instead of gzip JSON batches: a per-project **catalog** of event shapes, per-process
**alias tables** for repeated context, columnar encoding and **zstd with a project dictionary**. On research data it is about
10 bytes per event against about 100 for V1. The server contract is `docs/v7-transport.md` in the MortrisServer repository
(branch `feat/v7-transport`); this page describes what the SDK does.

## Turning it on

```csharp
Analytics.Initialize(new AnalyticsOptions
{
    ServerUrl = "https://analytics.example.com",
    ProjectId = "my-project",
    Environment = "production",
    UseTransportV7 = true,        // default false
});
```

Nothing else changes for the game. The SDK asks the server whether the project supports V7 and keeps sending V1 batches
when it does not: no catalog imported for the project, an older server, the native library missing on the device
(x86 emulators), or any protocol trouble. V7 never blocks delivery.

## What happens on the device

1. **Identity.** The Android queue (`Native~/android`) numbers every event 1, 2, 3, ... in the same SQLite transaction that stores it.
   The pair (installation, epoch, sequence) identifies an event; no random event id is sent. The server issues the epoch.
2. **Stream sync** (`POST /v2/streams/sync`): the SDK reports where its stream starts, its highest number and the ranges it dropped
   (events evicted, expired, cleared, or delivered through V1). The server answers with what it already holds
   (`ack_through`), the current catalog and dictionary ids, and the SDK deletes everything up to `ack_through`.
3. **Assets**: the catalog and dictionary are fetched once per id (`GET /v2/assets/...`), verified against their content id and
   cached under `persistentDataPath/daliys-analytics/v7`.
4. **Aliases** (`PUT /v2/streams/aliases`): the repeated context (session, app version, device, locale, timezone) is uploaded once
   per process and referenced by index in packets.
5. **Packets** (`POST /v2/events/packet`): up to 100 events, encoded on the worker thread. The response's `ack_through` settles
   the queue: only rows at or below it are deleted. Rejected events are final and count as settled.

## Fallback rules (always V1, never loss)

| Situation | Behaviour |
|---|---|
| Project has no catalog, or the server has no `/v2` routes | V1; asked again after an hour |
| An event shape is not in the catalog (new event or property) | that batch goes through V1; its rows are announced to the stream as dropped |
| Packet or alias answered with a protocol error | the attempt is retried, then V1; V7 is switched off for the process after 3 consecutive failures |
| The server acknowledges nothing we hold three times in a row | V1 for an hour |
| Native zstd cannot be loaded | V7 off for the process |
| Network errors, 408, 429, 5xx | same retry and backoff as V1 (`Retry-After` honoured) |
| 401 | re-registration, as for V1 |

**Duplicates across transports.** While a V7 stream is open, V1 batches carry each row's *derived* event id instead of its random one
(the same id the server derives from installation, epoch and sequence). If V7 already stored a row and its acknowledgement was lost,
a later V1 send of that row is recognised by the server as a duplicate instead of being stored twice. Acknowledgements are mapped back
to the queue's own ids before rows are deleted.

A counter that went backwards (a restored old queue) is detected by the server at sync (`409 stream_rollback`): the SDK continues
under a new epoch. Because the queue lives in `noBackupFilesDir`, Android backups do not restore it.

## Cost and limits

- A new installation downloads the catalog and dictionary (about 42 KB for Puzzle) and uploads its alias table before the first
  packet. For sessions under roughly 500 to 900 events V7 is not smaller than V1 on the wire. Ship assets in the build or cache them
  across sessions to avoid it (they are cached on disk per id).
- Numbers go through `float64` on the server, exactly as in V1.
- Android only. The native plugin ships for `arm64-v8a` and `armeabi-v7a` (and a macOS Editor library); other ABIs use V1.
- Plain `http://` is accepted only for `localhost`, `127.0.0.1` and `10.0.2.2` (development); everything else must be HTTPS.

## Verification map

| What | Where |
|---|---|
| Encoder vs the Python reference decoder (both catalog variants, all model flags, with/without dictionary) | `Native~/transport-tests` (`dotnet test`, set `M7_PYTHON`) |
| Encoder vs the server's Go decoder | MortrisServer `internal/transportv7` (`csharp_test.go`, packets exported by `ExportTests`) |
| Session state machine (rollback, alias gap/conflict, assets, 401/413/5xx, no progress, disabled native) | `Native~/transport-tests` `SessionTests` |
| Client to real server and PostgreSQL | `Native~/transport-tests/e2e/run-e2e.sh` |
| Java queue (journal, epoch, settle by sequence) | `AnalyticsQueueInstrumentationTest` on an emulator |
| IL2CPP player on an emulator against a local server | `Native~/transport-tests/e2e/run-device.sh` |
| Unity Editor (Mono) | `Tests/Runtime/V7TransportTests.cs` |
