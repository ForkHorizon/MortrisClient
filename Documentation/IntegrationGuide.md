# Mortris Analytics integration guide

## Purpose and scope

Mortris Analytics records semantic gameplay events in an Android-only durable
queue and uploads them to the configured Mortris ingestion server. It is not an
advertising SDK, crash reporter, identity provider, or general telemetry sink.
Do not send credentials, emails, names, advertising identifiers, or other PII.

The public namespace is currently `Daliys.Analytics` for compatibility. The
Unity Package Manager display name is **Mortris Analytics**.

## Install a fixed release

Use **Window > Package Manager > + > Add package from git URL**:

```text
git@github.com:ForkHorizon/MortrisClient.git#v0.1.4
```

Pinning a tag is required for reproducible game builds. Do not install from a
moving branch unless you are actively developing the SDK.

## Initialize once

Add one bootstrap component or use the game's existing startup service. Call
`Initialize` exactly once before any event can occur. Repeating it with the
same server, project, and environment is safe; a different configuration is an
error.

```csharp
using Daliys.Analytics;
using UnityEngine;

public sealed class MortrisAnalyticsBootstrap : MonoBehaviour
{
    private void Awake()
    {
        Analytics.Initialize(new AnalyticsOptions
        {
            ServerUrl = "https://your-mortris-server.example",
            ProjectId = "your-project-id",
            Environment = "production",
            AppVersion = Application.version,
            BuildNumber = Application.buildGUID,
            DebugLogging = false
        });
    }
}
```

`ServerUrl` must be an absolute HTTPS URL. `ProjectId` and `Environment` are
required. Get production values from the project owner; never put a test token
or installation credential in source control.

## Track semantic events

Call `Track` at the game's existing semantic boundary, not from every UI click,
frame update, or networking callback. During a comparison period, call Mortris
Analytics outside the old provider's readiness guard so both providers observe
the same game action.

```csharp
using System.Collections.Generic;
using Daliys.Analytics;

Analytics.Track("level_started", new Dictionary<string, object>
{
    ["level_id"] = levelId,
    ["level_number"] = levelNumber
});

Analytics.Track("level_completed", new Dictionary<string, object>
{
    ["level_id"] = levelId,
    ["level_number"] = levelNumber,
    ["duration_seconds"] = durationSeconds,
    ["completed"] = true
});
```

### Event contract

- Names and property keys: lowercase `snake_case`, starting with a letter; no
  trailing or repeated underscores. Event names cannot begin with `sys_`.
- Event name maximum: 64 characters. A maximum of 32 properties is accepted.
- Values: `null`, string, bool, integral numeric values, decimal, or finite
  float/double. Arrays, nested dictionaries, Unity objects, and non-finite
  numbers are rejected.
- Each string value is limited to 1 KiB; the encoded property object is limited
  to 8 KiB.
- Check the returned `TrackResult` only for diagnostics or a development-time
  assertion. Never block gameplay waiting for upload.

## Consent and lifecycle

Initialize first, then apply the user's saved consent decision:

```csharp
Analytics.SetCollectionEnabled(playerHasConsented);
```

Passing `false` clears pending data by default. Local opt-out always wins over
the server policy and cannot be re-enabled by the server.

The SDK persists and uploads in the background. `FlushAsync` is optional and
should only be called at a safe lifecycle boundary, such as an orderly app
pause; do not synchronously wait for it on the Unity main thread.

```csharp
private async void OnApplicationPause(bool paused)
{
    if (paused)
        await Analytics.FlushAsync();
}
```

## Delivery and diagnostics

`Track` returns `AcceptedToHandoff` when accepted for background persistence.
It can instead return `NotInitialized`, `CollectionDisabled`,
`InvalidEventName`, `InvalidProperties`, or `HandoffFull`.

`FlushAsync` returns one of these states:

| Status | Meaning |
| --- | --- |
| `Uploaded` | The current queue was acknowledged by the server. |
| `PersistedToDevice` | Events were durably saved; upload was not required yet. |
| `UploadDeferred` | Queue remains intact for a later retry. |
| `PersistenceUnavailable` | Running outside an Android player. |
| `PersistenceFailed` | Persistence failed; inspect development logs. |

`Analytics.GetDiagnostics()` exposes initialization, consent, in-memory handoff
count, handoff drops, and invalid-event count. It intentionally does not expose
installation credentials or event content.

## Android validation checklist

1. Build an IL2CPP Android player using the consuming game's real settings.
2. Start the game, trigger one start and one completion event, and check for
   `TrackResult.AcceptedToHandoff` in development instrumentation.
3. Run once offline, then restore connectivity and confirm the queue uploads.
4. Toggle consent off and confirm new events are not collected and queued data
   is cleared according to the product decision.
5. Compare event count, properties, ordering, and offline delay against the
   existing provider before retiring it.

## Supported platform

The durable delivery runtime is Android API 25+. In the Unity Editor and on
other platforms, `FlushAsync` returns `PersistenceUnavailable`; this is useful
for compilation and wiring checks but is not an upload test.
