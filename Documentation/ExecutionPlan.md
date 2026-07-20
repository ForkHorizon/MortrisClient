# Analytics SDK execution plan

This is the executable breakdown of the original implementation specification.
It preserves its non-negotiable delivery and privacy rules while keeping each
phase independently verifiable.

## U0 — package contract and testable handoff

- [x] Root package metadata for `com.daliys.analytics` and Unity `6000.3`.
- [x] Public initialization, tracking, consent, diagnostics, and flush result contracts.
- [x] Flat-property validation and reserved `sys_` name protection.
- [x] Bounded 256-event, newest-drop in-memory handoff.
- [x] Shared valid/invalid event fixtures and Unity test assembly.
- [x] Basic integration sample.
- [x] Unity 6000.3.16f1 EditMode suite passes (12 tests, verified in the live editor on 2026-07-20).

U0 deliberately has no durable queue or HTTP client. `FlushAsync` returns
`PersistenceUnavailable`; callers cannot mistake this scaffold for delivery.

## U1 — Android SQLite AAR

Progress: the reproducible Gradle wrapper, Java 11 release AAR, no-backup
database location, identity pair, WAL/NORMAL configuration, transactional
sequence assignment, bounded oldest-first eviction, batch reads, and
acknowledgement deletes are implemented. The AAR is copied to
`Runtime/Plugins/Android/daliys-analytics.aar` and is byte-for-byte identical
to the release build output. Device instrumentation on the Pixel 8 API 37
emulator verifies queue reopen persistence, installation identity stability,
oldest-row eviction, monotonic sequence ordering, corrupt-database reset, and
v1-to-v2 migration without queued-event loss. U1's native durability gate is
complete.

Build the owned Java 11 AAR around platform `SQLiteDatabase` in
`noBackupFilesDir`. It owns installation identity, the WAL/NORMAL queue,
schema upgrades, sequence assignment, queue bounds, acknowledgement deletes,
and corruption recovery. The native durability gate is verified on the device
emulator; U3 will cover Unity/IL2CPP packaging and API-level compatibility.

## U2 — C# worker and uploader

Progress: the Android-only JNI bridge, one-call 32-event persistence worker,
validated full-envelope serializer, durable-clear request, and asynchronous
delivery loop are implemented. The worker does no JSON, SQLite, JNI, or HTTP
work on the Unity main thread. It registers the persisted installation identity,
uploads gzip batches, deletes only IDs returned in `accepted`, `duplicates`, or
`rejected` (omitted IDs stay queued), retries transport/malformed-success
failures with exponential backoff and `Retry-After`, re-registers once after a
`401`, halves an oversized batch, and applies the server policy only after
acknowledgements are deleted. `install_conflict` pauses delivery without
changing the queue or identity. Local consent remains an independent gate, so a
server `active` policy cannot re-enable a local opt-out. It uploads at the
configured event threshold or interval, or immediately on `FlushAsync`.

The server contract is the three endpoints: install registration, event
batches, and client policy. U2's device-level exit gate is complete. On
2026-07-20 the Pixel 8 API 37 emulator registered and delivered a real event
to `mortris-prod`; the run found and fixed the missing JVM attachment for the
background JNI worker. The controlled `mortris-sdk-test` server then verified
lost acknowledgement/duplicate delivery, one-time `401` re-registration,
two-event `413` splitting, `429` plus `Retry-After`, and the `active`,
`pause_upload`, and `disable_collection` policy modes. The temporary test
header hook and launcher probe were removed after the run.

## U3 — Unity package/build proof

Progress: on 2026-07-20 Unity `6000.3.16f1` built, installed, and launched the
actual package on the Pixel 8 API 37 Android emulator. The release player used
IL2CPP, ARM64, and managed stripping; Unity's IL2CPP build input included
`Daliys.Analytics.dll`, and the launched process remained healthy. A separate
custom-Gradle-template compatibility build with both ARMv7 and ARM64 succeeded;
its APK contains `libmain.so`, `libunity.so`, and `libil2cpp.so` for both
ABIs. That APK then installed and launched without fatal runtime errors on new
API 25 and API 35 emulators. The project settings and temporary Gradle template
were restored after the proof. U3's Android packaging compatibility gate is
complete.

Test the actual package in Unity `6000.3.16f1` against Android API 25/35,
IL2CPP, managed stripping, ARMv7/ARM64, and the consuming game's custom Gradle
templates. The package must add no Android permissions, services, Kotlin,
AndroidX, Room, WorkManager, or second SQLite engine.

## U4 — game semantics and parity

Integrate only at the consumer's existing semantic start/complete methods,
outside its existing analytics-provider readiness guard. Dual-send during the
comparison period and explain any count, property, ordering, or offline-delay
difference before retirement of the old provider.

## U5 — release hardening

Soak lifecycle, malformed server, queue pressure, clock changes, policy,
consent reset, upgrade, process-kill, and low-end Android scenarios. Publish
only when the delivery guarantees and documented loss modes are demonstrated.
