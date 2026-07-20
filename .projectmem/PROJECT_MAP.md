# Project Map - MortrisClient

Status: U0 package contract and test scaffold in progress.

## Project purpose
Independent Unity 6 playground for developing and validating an offline-first analytics SDK before any game integration. The future deliverable is an installable UPM package with an Android SQLite bridge, samples, and automated tests; Puzzle is a later consumer, not part of this repository.

## Structure
- `AGENTS.md` — project-level agent instructions, including codebase-memory discovery guidance.
- `CLAUDE.md` — ProjectMem workflow bridge for agents that use Claude-compatible instructions.
- `.gitignore` — Unity, IDE, ProjectMem runtime, local MCP credential, and Graphify output exclusions.
- `package.json` — UPM metadata for `com.daliys.analytics`, pinned to Unity 6000.3 and the Unity Newtonsoft package.
- `README.md` — U0 package status and local UPM installation example.
- `Documentation/ExecutionPlan.md` — recalculated phase gates from U0 through release hardening.
- `Runtime/` — platform-neutral U0 public API, validation, diagnostics, and bounded handoff.
  - `Runtime/Analytics.cs` — static package entry point.
  - `Runtime/AnalyticsOptions.cs` — safe public configuration surface.
  - `Runtime/Internal/EventValidator.cs` — public event/property contract enforcement.
  - `Runtime/Internal/AnalyticsRuntime.cs` — validates and routes events to the bounded persistence handoff.
  - `Runtime/Internal/AnalyticsPersistenceWorker.cs` — background 32-event batching; retains events until JNI persistence succeeds.
  - `Runtime/Internal/AndroidQueueBridge.cs` — Android-only JNI adapter for the owned Java queue AAR.
  - `Runtime/Internal/PersistenceEventSerializer.cs` — dependency-free JSON envelope serializer for the validated primitive-property contract.
- `Tests/` — Unity test assembly and shared event-validation fixtures.
- `Samples~/BasicIntegration/` — minimal Unity component showing package bootstrap and a semantic event.
- `Native~/android/` — reproducible Java 11 Android AAR source.
  - `Native~/android/analytics/src/main/java/com/daliys/analytics/AnalyticsQueue.java` — SQLite identity and pending-event queue.
  - `Native~/android/analytics/src/main/java/com/daliys/analytics/QueueResult.java` — JNI-friendly queue operation result.
  - `Native~/android/analytics/src/androidTest/java/com/daliys/analytics/AnalyticsQueueInstrumentationTest.java` — dependency-free Pixel 8 device checks for reopen persistence, eviction, corruption reset, and v1-to-v2 upgrade.
  - `Native~/android/gradlew` — pinned Gradle wrapper for native builds.
- `Runtime/Plugins/Android/daliys-analytics.aar` — verified release AAR built from `Native~/android/`.
- `.projectmem/` — persistent project decision history and maintained project map.
  - `.projectmem/config.toml` — ProjectMem retention and project description settings.
  - `.projectmem/PROJECT_MAP.md` — this navigable structural map.
  - `.projectmem/plan.md` — editable product intent and implementation plan.
- `.serena/` — local Serena project configuration; cache and machine-specific settings are ignored.
- `graphify-out/.gitignore` — dedicated guard that keeps regenerated Graphify output local.

## Relationships
- `AGENTS.md` directs code discovery through the codebase-memory graph once SDK source is added.
- `.projectmem/PROJECT_MAP.md` describes the repository structure while `.projectmem/events.jsonl` records development history locally.
- `.gitignore` preserves curated ProjectMem configuration/map/plan but excludes ProjectMem runtime state and all generated Graphify artifacts.
- `Runtime/Analytics.cs` forwards public calls to `Runtime/Internal/AnalyticsRuntime.cs`, which validates and captures events before the background persistence worker writes Android batches through JNI.
- `Tests/Runtime/AnalyticsTrackTests.cs` verifies the U0 API contract and handoff bounds against `Runtime/`.
- `Runtime/Internal/AnalyticsPersistenceWorker.cs` passes one validated batch to `AnalyticsQueue.enqueueBatch` through `Runtime/Internal/AndroidQueueBridge.cs`; registration, upload, acknowledgement, and retry remain future U2 work.
- Future Unity package, Android bridge, samples, and tests will be indexed by both codebase-memory and Graphify after they are added.
