# Events on their way to the server: buffer, queue, batches, retries

How an event travels after `Track()` and what you can tune. Numbers come from the real Puzzle events (239 installs, about one million events) and from the comparison run of 26.10.2026 (`comparison-run~/REPORT.md`).

## What a game really sends

| | Puzzle (real) |
|---|---|
| events in 200 ms | median 2, 99% ≤ 4, most 12 |
| events per second | median 2, 99% ≤ 6, most 49 |
| events in an active minute | on average 46, 99% ≤ 111 |
| events in one hour (per player) | median 1 171, 99% ≤ 4 198, most 4 477 |
| events in four hours | 99% ≤ 9 169, most 12 556 |

One event costs 136 bytes (casual), 205 (telemetry), 509 (varied) or 756 (Puzzle with UUID strings) in the queue, plus about 40 bytes of bookkeeping.

## 1. The in-memory buffer

`Track()` encodes the event once and puts the record into a buffer (about 2 µs). Every `EventBufferWindow` (200 ms) a background thread writes everything in it to the on-device queue in one transaction. The buffer holds at most `EventBufferBytes` (2 MB by default, only bytes are counted): that is about 2 600 Puzzle events or 14 000 casual events, and a game never has more than a few dozen in it.

When a burst fills it, **`Track()` writes the buffer to the queue itself and goes on**. Nothing is lost; the calling frame is longer. `AnalyticsDiagnostics.BufferFlushedByTrack` counts how often this happened. A game that has to export many events at once should call `Analytics.TrackBatchAsync` instead.

## 2. `TrackBatchAsync`: many events without a long frame

```csharp
var events = new List<BatchEvent>();
foreach (var row in myOwnStatistics)
    events.Add(new BatchEvent("stats_row", row.Properties, row.Time));   // Time: when it happened (optional)
BatchResult result = await Analytics.TrackBatchAsync(events);
```

The events are encoded on a pool thread and written to the queue in chunks of at most 500 events, behind whatever `Track()` has buffered so far. Do not change the list or the dictionaries until the task completes. The per-name rate limit does not apply. Sequence numbers of a batch and of `Track()` calls made while it runs may interleave; event times are exact. `BatchResult` tells how many events were stored, refused as invalid or could not be stored.

## 3. The on-device queue

Events wait there until the server confirms them (by sequence number), also when the player is offline.

| Option | Default | |
|---|---|---|
| `DurableByteLimit` | 64 MB | the limit that matters: events plus about 40 bytes each. Holds about 80 000 Puzzle events, 355 000 casual events |
| `DurableEventLimit` | 0 = no limit | rarely needed |
| `MaxEventAge` | 0 = never | a player who returns after two weeks still delivers; the server recomputes statistics for late events |

When the byte limit is hit the **oldest** events are dropped. The drop is counted (`AnalyticsDiagnostics.QueueEvictedEvents`) and reported to the server as lost sequence numbers. An ordinary player needs about 1–4 MB for an hour offline and about 10 MB for four hours; 64 MB covers more than a day of continuous play at the average rate (46 events a minute).

## 4. When and how much is sent

| Option | Default | |
|---|---|---|
| `UploadInterval` | 120 s | at most this long between uploads |
| `UploadEventThreshold` | 200 | this many queued events start an upload sooner |
| `MaxPacketEvents` | 200 | events per packet while few are waiting |
| `BacklogPacketEvents` | 500 | events per packet while more than twice `MaxPacketEvents` are waiting |
| `BacklogPacketPause` | 300 ms | pause between packets of a backlog, so draining does not compete with the game |
| `AdaptivePacketSize` | true | smaller packets after a failed or very slow request, growing back after fast ones |

`options.UseProfile(...)` sets the first three at once:

| Profile | Interval / threshold / packet | Use |
|---|---|---|
| `Realtime` | 5 s / 20 / 200 | live dashboards; the most traffic per event |
| `Standard` | 120 s / 200 / 200 | default |
| `TrafficSaver` | 5 min / 500 / 500 | fewest requests and TLS handshakes; events arrive up to five minutes late |

Why bigger is cheaper (V8, bytes per event, request headers excluded): packet of 10 events 57, 30 → 29, 100 → 18, 200 → 16; one TLS handshake costs 4–5 KB, so at one event per second the handshakes dominate (116 bytes per event including TLS against 27 at thirty events per second). Larger packets also mean fewer requests against the server's limits.

Adaptive sizing needs no permission and no guess about the kind of network (2G/3G/4G cannot be read without `READ_PHONE_STATE`): it only looks at how long the last request took. A request over three seconds does not grow the packet, over eight seconds it shrinks by a quarter, a failure halves it (never below 20 events).

## 5. When the upload fails

| Situation | What the SDK does |
|---|---|
| No network (`Application.internetReachability == NotReachable`, read every 5 s, no permission needed) | makes no attempt; when the network returns, uploads after 0–5 s of random delay and forgets the back-off |
| Network, but the server answers 5xx or does not answer | waits 5 s, 10 s, 20 s … up to 5 minutes; each wait is spread over the upper half of its step ("equal jitter") so clients that failed together do not return together |
| 429 | waits for the `Retry-After` the server sends (at most 10 minutes, plus up to 10% spread) |
| 401 | sends `hello` again; 400 → the same packet is not repeated |
| The player returns to the game | forgets the back-off, so whatever is due goes out without waiting for the old retry time |
| "Network" without internet (a portal, a dead Wi-Fi) | handled like a server that does not answer |

Forced uploads (`FlushAsync`, the upload when the game goes to the background) ignore the back-off and the pauses.

## 6. Server limits

Per project, set with `analytics-server set-ingest-profile --project <id> --profile standard|elevated|unlimited`. A server without migration 0035 treats every project as `standard`.

| | standard | elevated (×10) |
|---|---|---|
| events per installation | 3 000 a minute, burst 30 000 | 30 000 a minute, burst 300 000 |
| requests per installation | 30 a minute, burst 60 | 300 a minute, burst 600 |
| requests per project | 30 a second, burst 100 | 300 a second, burst 1 000 |

`unlimited` switches the per-installation and per-project limits off. The per-address limit (500 requests a second, burst 1 000, because many players share an address behind a mobile operator's NAT) stays. All values can be overridden by environment (`MORTRIS_INGEST_*`, see `internal/ingest/ingest_limits.go`). A refused request answers 429 with a `Retry-After` computed from the bucket.
