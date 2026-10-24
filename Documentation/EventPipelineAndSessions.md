# Event pipeline and sessions

This describes what happens between `Analytics.Track()` and the server, and how the SDK knows when the player left the game.

## From `Track()` to the durable queue

1. `Track()` validates the name and properties, then writes the event once as a **binary record** (`Runtime/Internal/Transport/EventRecord.cs`): ids,
   timestamps, the device context (encoded once per process), the name and the typed properties. No JSON is built or parsed anywhere on the way.
2. The record goes into an in-memory **buffer** (`EventBuffer`). A timer (`AnalyticsOptions.EventBufferWindow`, 200 ms by default) or a size threshold
   (128 records) hands the whole buffer to the Android queue in **one call and one SQLite transaction**. The queue numbers the records.
3. The queue stores each record as a blob. It never parses events; its row counters and the next sequence number live in memory.
4. The uploader reads rows back as records. Transport V7 packs them into columns directly from the records; V1 renders its JSON batch from them.
   Rows written by earlier SDK versions (JSON payloads) are converted when they are read.

What this means for the game:

- Events are in memory for at most `EventBufferWindow` before they are durable. A process killed without warning loses at most that window.
- Leaving the game writes immediately (below), so the normal "player minimised the game" path loses nothing.
- Uploading is unchanged: `UploadInterval` / `UploadEventThreshold`, and `FlushAsync()` still forces a write and an upload.
- `AnalyticsOptions.EventBufferWindow = TimeSpan.Zero` writes every event at once (the old behaviour, much more CPU).

## Sessions and leaving the game

The SDK installs a hidden object that receives Unity's `OnApplicationPause`, `OnApplicationFocus` and `OnApplicationQuit`.

| Moment | What the SDK does |
|---|---|
| Player minimises / leaves (`OnApplicationPause(true)`) | Emits `sys_app_background`, writes the buffer and the session state to the durable queue on the calling thread, does not upload |
| Window loses focus (`OnApplicationFocus(false)`) | Writes the buffer on the calling thread |
| Player returns within `SessionTimeout` (default 5 min) | Same session; emits `sys_app_foreground` (`new_session = false`) |
| Player returns after `SessionTimeout` | Ends the old session **at the moment the player left** (`sys_session_end`, reason `timeout`), starts a new one (`sys_session_start`), emits `sys_app_foreground` (`new_session = true`) |
| Application quits | Emits `sys_session_end` (reason `quit`) and writes immediately |
| Process died without any of the above | At the next launch the SDK closes the previous session (see below) |

Every 30 seconds in the foreground the SDK saves "I am alive" (one small write). If the process vanishes, the next launch emits
`sys_session_end` for the old session id:

- left in the background earlier: ends when the player left (`background_killed`);
- killed in the game: ends at the time Android reports the process died (Android 11+ `ApplicationExitInfo`), otherwise at the last "alive" mark. The
  reason is the platform's: `crash`, `native_crash`, `anr`, `low_memory`, `signaled`, `user_requested`, ... or `unknown_kill` when Android has no record.

### System events

All carry the session id and time they belong to, not the time they were sent. Names starting with `sys_` stay reserved: games cannot track them.

| Event | Properties |
|---|---|
| `sys_session_start` | `cold_start` (bool) |
| `sys_app_background` | `active_ms` (int, foreground time so far), `reason` (string) |
| `sys_app_foreground` | `paused_ms` (int), `new_session` (bool) |
| `sys_session_end` | `duration_ms` (int), `active_ms` (int), `reason` (string), `background` (bool) |

**Server catalog.** With transport V7 the project's catalog must contain these four shapes, otherwise a packet holding one is sent through V1 (correct,
but about five times bigger). `Native~/transport-tests/tools/add_lifecycle_shapes.py IN.json OUT.json` adds them to a catalog and keeps the server's
rules (event ids are alphabetical ranks, keys sorted, masks recomputed); existing shape ids do not move.

## Costs (measured)

See `profiling-run~/REPORT.md` and `profiling-run~/RESULTS_AFTER.md` for the emulator matrix and the host allocation profile; the figures that matter:
the `Track()` body is about 2 µs and 80 bytes of garbage on the host, the whole write to the durable queue happens once per window instead of once per event.
