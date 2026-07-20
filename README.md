# Daliys Analytics

`com.daliys.analytics` is a standalone Unity Package Manager package for safe,
offline-first Android game analytics.

## Current milestone: U2 delivery path

The package includes the U0 public contract, the Java 11 Android SQLite queue,
and the U2 delivery path. On Android, a background C# worker serializes at most
32 validated events into one JNI call to the owned AAR, then registers its
persisted installation identity and uploads gzip batches. It removes a durable
row only after the server acknowledges that event as accepted, duplicate, or
rejected. Transport failures, malformed successes, rate limits, and 5xx
responses leave rows queued and back off; a `413` halves the batch.

The server can pause upload or disable collection through `client_policy`.
`FlushAsync` reports whether data was persisted, uploaded, or deferred. You may
set `AppVersion` and `BuildNumber` in `AnalyticsOptions` to override Unity's
runtime values when your build pipeline has a canonical version source.

The native queue is verified on a Pixel 8 API 37 emulator for persistence
across reopen, stable installation identity, oldest-event eviction, corrupt
database reset, and migration from schema v1 to v2 without event loss.

## Local package use

In a Unity project's `Packages/manifest.json`, add a local dependency while
developing:

```json
"com.daliys.analytics": "file:../Assets/MortrisClient"
```

Initialize once during game bootstrap, then track only semantic gameplay events:

```csharp
Analytics.Initialize(new AnalyticsOptions {
    ServerUrl = "https://analytics.example.com",
    ProjectId = "puzzle-development",
    Environment = "development"
});

Analytics.Track("level_start", new Dictionary<string, object> {
    ["house_id"] = "rome_01",
    ["level_number"] = 1
});
```

`Track` accepts only flat, primitive properties and returns a `TrackResult`.
It never encodes JSON, accesses SQLite/JNI, or performs networking on the
calling thread; that work happens in the Android persistence worker.
