# V8 transport

V8 is the SDK's binary transport and the one being developed (V1 gzip JSON stays only as the fallback). Events travel as zstd-compressed columns,
identified by a sequence number instead of a random UUID; the server issues a short installation id and a token, the event shapes are learned by the SDK as
events arrive (no catalog to import), a normal launch sends its first packet without a handshake, the server's answer is a few bytes, and the server trains a
compression dictionary for the project by itself. The contract is `docs/v8-transport.md` in the MortrisServer repository (a copy is
`Theory~/transport-v8/SERVER_CONTRACT.md`); the decisions and measurements are in `Theory~/transport-v8/PROTOCOL.md`.

## Turning it off

```csharp
Analytics.Initialize(new AnalyticsOptions
{
    ServerUrl = "https://analytics.example.com",
    ProjectId = "my-project",
    Environment = "production",
    UseTransportV8 = false,       // default true: V8, with V1 as the fallback
});
```

Whatever V8 cannot do (an old server, no keys on the server, a shape the project refuses, no native zstd), the SDK sends through V1, and the batch
belongs to the same installation: the server hands the SDK its V1 identity at the first hello.

## What changes for the game

- **Numbers keep their type.** A `float` is sent as a float32 and a `double` as a float64 whatever their value, so an event's shape does not change when a float is
  `0` or `0.5`. A float is read by the server as its shortest decimal text (`12.345679`, not `12.34567928314209`).
- **No UUIDs in events.** Use `Analytics.NextId("attempt")` (1, 2, 3...) for ids the game numbers itself. The SDK stores the counter in the same transaction as the
  events that used it, so a number the server has seen is not handed out again after a crash. The server's key for such an id is the pair (installation, number).
- **New events and properties need no setup.** The first packet that carries a new shape registers it with the project (unless the project is `strict_catalog`).

## What the SDK keeps on the device

Token, nonce, the project's shape table and the counts of what the server holds live in the queue's durable storage (`v8.*` keys), so a launch needs a `hello` only
when there is no token, no stream, or the server says something is off. Asset (dictionary) files are cached under `persistentDataPath/daliys-analytics/v8`.

## Measured (Android emulator, IL2CPP, local V8 server, real events of the Puzzle project)

Bytes per event on the wire (packets only, headers and TLS not included):

| Scenario | V1 (gzip) | V8, events as the game sends them today | V8, event content of decision D9 and D10 |
|---|---:|---:|---:|
| 20 events per frame, 2800 events | 70.2 | 21.1 | **10.1** |
| 1 event per frame, 1200 events | 76.3 | 24.1 | **12.7** |
| 100 events at once, 500 events | 68.8 | 26.6 | **15.5** |
| 1 event a second, 90 events | 210.6 | 91.6 | **65.1** |
| 17 events, one every 6 s | 445.9 | 253.3 | **197.5** |

Over real HTTP against the Go server on the host, 6000 events of the decided content take 9.07 bytes each, 8.09 once the server has trained its dictionary.

## Identity on the device

The Android queue (`Native~/android`) numbers every event 1, 2, 3, ... in the same SQLite transaction that stores it. The triple (installation, epoch, sequence)
identifies an event; the server issues the epoch. The server answers with `ack`, and the SDK deletes only rows at or below it; rejected events are final and count
as settled. While a stream is open, V1 fallback batches carry each row's *derived* event id, so a row V8 already stored is a duplicate on V1, not a copy.
A counter that went backwards (a restored old queue) is answered with `409 stream_rollback` and the SDK continues under a new epoch. The queue lives in
`noBackupFilesDir`, so Android backups do not restore it.

## Limits

- Android only. The native zstd plugin ships for `arm64-v8a` and `armeabi-v7a` (and a macOS Editor library); other ABIs, or a device where it cannot load, use V1.
- Plain `http://` is accepted only for `localhost`, `127.0.0.1` and `10.0.2.2` (development); everything else must be HTTPS.
- Network errors, 408, 429 and 5xx use the same retry and backoff as V1 (`Retry-After` honoured).

## Verification

| What | Where |
|---|---|
| Session state machine against a fake server | `Native~/transport-tests` `V8SessionTests` (`FakeV8Server`) |
| Client against the real Go server and PostgreSQL | `Native~/transport-tests` `E2EV8Tests`, `e2e/run-e2e.sh` |
| Allocation per stage | `Native~/transport-tests` `V8StageAllocationTests` |
| IL2CPP player on an emulator against a local server | `Native~/transport-tests/e2e/run-device.sh` |
