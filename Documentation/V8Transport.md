# V8 transport (opt-in)

V8 sends events as compact binary packets like V7, and changes everything around them: the server issues a short installation id and a token, the event shapes
are learned by the SDK as events arrive (no catalog to import), a normal launch sends its first packet without a handshake, the server's answer is a few bytes, and
the server trains a compression dictionary for the project by itself. The contract is `docs/v8-transport.md` in the MortrisServer repository
(branch `feat/v8-transport`; a copy is `Theory~/transport-v8/SERVER_CONTRACT.md`); the decisions and measurements are in `Theory~/transport-v8/PROTOCOL.md`.

## Turning it on

```csharp
Analytics.Initialize(new AnalyticsOptions
{
    ServerUrl = "https://analytics.example.com",
    ProjectId = "my-project",
    Environment = "production",
    UseTransportV8 = true,        // default false; replaces UseTransportV7
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
