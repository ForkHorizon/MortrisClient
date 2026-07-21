# Mortris Analytics

`com.daliys.analytics` is an offline-first Unity Package Manager package for
Mortris Android game analytics. It persists validated gameplay events locally,
then registers and uploads them in the background when the network is usable.

Start with the [integration guide](Documentation/IntegrationGuide.md). For an
agent making the integration, use the concise
[AI integration brief](Documentation/AIIntegration.md). SDK contributors can
use the [development and validation guide](Documentation/Development.md).

## What it guarantees

- Android-only durable SQLite queue in the app's no-backup storage.
- At-least-once delivery: an event remains queued until the server acknowledges
  it as accepted, duplicate, or permanently rejected.
- Gzip batching, retry/backoff, `Retry-After`, one `401` re-registration, and
  batch splitting for `413` responses.
- Local consent always overrides server policy. Disabling collection clears
  pending data by default.
- No JSON, SQLite, JNI, or HTTP work on the Unity calling thread.

## Install

In Unity Package Manager, choose **Add package from git URL** and use the
current release tag:

```text
git@github.com:ForkHorizon/MortrisClient.git#v0.1.4
```

For a local checkout during SDK development:

```json
"com.daliys.analytics": "file:../Assets/MortrisClient"
```

## Minimal bootstrap

The visible package name is **Mortris Analytics**. The stable technical package
ID and C# namespace remain `com.daliys.analytics` and `Daliys.Analytics`.

```csharp
using Daliys.Analytics;

Analytics.Initialize(new AnalyticsOptions
{
    ServerUrl = "https://your-mortris-server.example",
    ProjectId = "your-project-id",
    Environment = "production"
});
```

Call `Initialize` once during bootstrap, then call `Track` only at semantic
gameplay boundaries such as level start and level completion. See the
[integration guide](Documentation/IntegrationGuide.md) for property rules,
consent, lifecycle, diagnostics, and Android validation.

## Compatibility and proof

The package targets Unity `6000.3` and Android API 25+. Its Android queue,
uploader contract, IL2CPP/managed-stripping package build, ARMv7/ARM64 APK,
and API 25/35/37 launches have been verified. The current delivery and future
hardening plan is in [ExecutionPlan.md](Documentation/ExecutionPlan.md).
