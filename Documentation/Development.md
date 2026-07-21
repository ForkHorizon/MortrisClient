# Mortris Analytics development and validation

This guide is for SDK contributors. It is not required to integrate the package
into a game.

## Repository boundaries

- Source package root: this repository root.
- Managed Unity runtime: `Runtime/`.
- Android queue source: `Native~/android/`.
- Packaged Android AAR: `Runtime/Plugins/Android/daliys-analytics.aar`.
- Generated Unity, Gradle, ProjectMem runtime, Graphify, and local connection
  state stay ignored; do not add them to a release.

## Native Java checks

Use the installed Android SDK explicitly. This runs JVM unit tests without
requiring a device:

```bash
cd Native~/android
ANDROID_HOME=/Users/daliys/Library/Android/sdk ./gradlew test --no-daemon
```

Build the release AAR whenever Java queue code changes, then verify that the
output is the file packaged at `Runtime/Plugins/Android/daliys-analytics.aar`.

## Android device queue test

The owned queue uses a dependency-free `Instrumentation` runner. The
reproducible device command avoids the Android Gradle Plugin's optional UTP
host-test download and its adb-path ambiguity:

```bash
adb -s emulator-5554 shell am instrument -w -r \
  com.daliys.analytics.test/com.daliys.analytics.AnalyticsQueueInstrumentationTest
```

The expected success line is:

```text
INSTRUMENTATION_RESULT: stream=U1 device queue tests passed.
```

This covers queue reopen persistence, stable identity, bounded oldest-event
eviction, corruption reset, schema migration, and identity reset sequence
continuity. It has been verified on the Android API 37 emulator.

## Unity/package checks

1. Open the Unity 6000.3 project containing this package.
2. Run the EditMode tests under `Tests/Runtime`.
3. Build a release IL2CPP Android player with managed stripping enabled.
4. Confirm the package AAR and `Daliys.Analytics.dll` are included.
5. Install and launch on supported Android API levels.

The existing package proof covers ARMv7 and ARM64 with a custom Gradle template
and launch verification on API 25, 35, and 37.

## Release checklist

1. Update `package.json` version and `AnalyticsDeviceContext.SdkVersion`
   together.
2. Update `CHANGELOG.md` before tagging.
3. Validate the manifest JSON, native tests, and Unity package build.
4. Commit only source, docs, `.meta` files, and the packaged AAR.
5. Create and publish a matching immutable `vX.Y.Z` Git tag.
6. Install that tag in a clean Unity project to verify Package Manager metadata
   and absence of immutable-folder warnings.
