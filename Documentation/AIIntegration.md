# AI integration brief

Use this file when assigning Mortris Analytics integration to an AI coding
agent. It defines the allowed change boundary and verification target.

## Objective

Install **Mortris Analytics** into the consuming Unity game and dual-send a
small set of existing semantic gameplay events. Do not modify this package's
source as part of a consumer integration.

## Package and API

- Git package: `git@github.com:ForkHorizon/MortrisClient.git#v0.1.4`
- UPM package identifier: `com.daliys.analytics`
- C# namespace: `Daliys.Analytics`
- Public calls: `Analytics.Initialize`, `Analytics.Track`,
  `Analytics.SetCollectionEnabled`, `Analytics.FlushAsync`, and
  `Analytics.GetDiagnostics`.

## Required implementation

1. Add the Git package to `Packages/manifest.json` through Unity Package
   Manager.
2. Initialize once in the game's existing bootstrap path with the owner-supplied
   HTTPS server URL, project ID, environment, app version, and build number.
3. Apply persisted user consent after initialization. An opt-out must call
   `Analytics.SetCollectionEnabled(false)`.
4. Add `Analytics.Track` calls immediately beside the existing semantic
   start/complete calls. Keep the current analytics provider in place during
   comparison.
5. Use lowercase snake_case event names and flat primitive properties only.
6. Never put a credential, test token, PII, nested object, or array in event
   properties or repository files.

## Constraints

- Do not call analytics from `Update`, render paths, or every UI interaction.
- Do not wait synchronously for `FlushAsync`; gameplay must never depend on
  upload success.
- Do not wrap Mortris calls in another provider's readiness guard.
- Do not rename the UPM identifier or `Daliys.Analytics` namespace without an
  explicit package-major-version migration.
- The durable delivery path is Android-only; Editor results are wiring checks,
  not delivery proof.

## Done when

- The Android player compiles with the consuming game's real IL2CPP settings.
- Start and completion actions return `AcceptedToHandoff` in development.
- An offline event uploads after connectivity returns.
- Consent opt-out prevents collection and clears queued data as intended.
- The comparison report explains any difference from the existing provider in
  count, properties, ordering, or offline delay.

Read [IntegrationGuide.md](IntegrationGuide.md) for the full API and lifecycle
contract. SDK contributors should also read [Development.md](Development.md).
