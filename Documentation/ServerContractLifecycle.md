# What the server must accept for the lifecycle events

The SDK now emits session events (`Documentation/EventPipelineAndSessions.md`). The V7-branch server (`MortrisServer`, `feat/v7-transport`) only whitelists three
SDK-owned names in `internal/contracts/validate.go`:

```go
var ReservedSystemEvents = map[string]bool{
    "sys_session_start":  true,
    "sys_app_background": true,
    "sys_sdk_health":     true,
}
```

Anything else starting with `sys_` is rejected with `reserved_event_name` (the batch answers 200 and lists the event as rejected, so the SDK deletes it and the
data is lost). Verified on the emulator: against the unmodified server `sys_app_foreground` and `sys_session_end` were rejected, `sys_session_start` and
`sys_app_background` were stored.

## Required server changes

1. Add `sys_app_foreground` and `sys_session_end` to `ReservedSystemEvents` (they then get `event_kind = "system"`, no catalog lookup, no drift check).
2. V7 projects: add the four shapes to the project's catalog (`Native~/transport-tests/tools/add_lifecycle_shapes.py IN.json OUT.json`), then re-import with
   `import-transport-assets`. Without them a packet that contains one of these events is sent through V1 instead of V7.
3. Metrics (`docs/metrics.md`, "Observed session duration"): the file says there is no guaranteed session-end event. There now is one in most cases, so the
   metric can use it. Rules the SDK follows:
   - `sys_session_end` carries `duration_ms` (wall time from session start to the end moment), `active_ms` (time in the foreground), `reason` and `background`.
     `occurred_at_client` is the end moment, not the time the event was sent; `session_elapsed_ms` equals `duration_ms`.
   - `reason`: `timeout` (player came back after `SessionTimeout`), `quit`, `background_killed` (the player had left, the process was killed later), and for a
     process that died in the game the Android exit reason: `crash`, `native_crash`, `anr`, `low_memory`, `signaled`, `user_requested`, `user_stopped`,
     `exit_self`, `excessive_resource_usage`, `other`, ... or `unknown_kill` when Android kept no record (before Android 11 or no history).
   - A session can still have no end event (the next launch never happened). Do not infer a "true" end for those.
   - `sys_app_background.active_ms` is the foreground time of the session so far; `sys_app_foreground.paused_ms` is how long the player was away.

The shapes are small and fixed, so adding them costs a few bytes per session. The rest of the wire protocol (`/v2/*`, `/v1/events/batch`) is unchanged.
