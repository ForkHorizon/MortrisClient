// Tracks play sessions and produces the session lifecycle events.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using Daliys.Analytics.Internal.Transport;

namespace Daliys.Analytics.Internal.Session
{
    /// <summary>Receives the session lifecycle events the tracker produces. Each belongs to the session id and moment given, not to "now".</summary>
    internal interface ISessionEventSink
    {
        void Emit(string name, Guid sessionId, long occurredAtUnixMs, long sessionElapsedMs, IReadOnlyDictionary<string, object> properties);
    }

    /// <summary>The session new events are stamped with. Replaced as a whole when a session rotates.</summary>
    internal sealed class SessionInfo
    {
        internal SessionInfo(Guid id, long startUnixMs) { Id = id; StartUnixMs = startUnixMs; }
        internal Guid Id { get; }
        internal long StartUnixMs { get; }
    }

    /// <summary>
    /// Knows when the player is in the game, left it, or came back, and turns that into events:
    /// <c>sys_session_start</c>, <c>sys_app_background</c>, <c>sys_app_foreground</c> and <c>sys_session_end</c> (also for a previous process that died
    /// without ending its session, see <see cref="Recover"/>). Pure logic with an injectable clock; the Unity lifecycle hooks call into it.
    /// A session ends when the player stays away longer than the timeout, on quit, or - when the process vanished - at the last moment it was known to be alive.
    /// </summary>
    internal sealed class SessionTracker
    {
        internal const string SessionStart = "sys_session_start", AppBackground = "sys_app_background", AppForeground = "sys_app_foreground", SessionEnd = "sys_session_end";
        private const int StateVersionNumber = 1;

        private readonly object _sync = new object();
        private readonly Func<long> _nowMs;
        private readonly TimeSpan _timeout;
        private readonly ISessionEventSink _sink;
        private readonly Func<Guid> _newId;
        private SessionInfo _current;
        private long _activeMs;          // foreground time accumulated before the current foreground stretch
        private long _foregroundSince;   // unix ms the current foreground stretch began (0 = in background)
        private long _backgroundAt;      // unix ms the player left (0 = in the game)
        private long _aliveAt;
        private bool _ended;
        private int _version;

        internal SessionTracker(Func<long> nowMs, TimeSpan timeout, ISessionEventSink sink, Func<Guid> newId = null)
        {
            _nowMs = nowMs; _timeout = timeout; _sink = sink; _newId = newId ?? Guid.NewGuid;
        }

        internal SessionInfo Current => System.Threading.Volatile.Read(ref _current);
        /// <summary>Changes whenever <see cref="Snapshot"/> would return something new.</summary>
        internal int StateVersion => System.Threading.Volatile.Read(ref _version);

        /// <summary>Begins the first session of the process.</summary>
        internal void Start()
        {
            lock (_sync)
            {
                BeginSession(_nowMs(), coldStart: true);
            }
        }

        /// <summary>Unity's OnApplicationPause: true when the player left, false when they came back.</summary>
        internal void OnPause(bool paused)
        {
            lock (_sync)
            {
                if (_current == null || _ended) return;
                var now = _nowMs();
                if (paused)
                {
                    if (_backgroundAt != 0) return;
                    _activeMs += Math.Max(0, now - _foregroundSince);
                    _foregroundSince = 0; _backgroundAt = now; _aliveAt = now;
                    Emit(AppBackground, _current, now, new Dictionary<string, object> { { "active_ms", _activeMs }, { "reason", "pause" } });
                }
                else
                {
                    if (_backgroundAt == 0) return;
                    var left = _backgroundAt; var gap = Math.Max(0, now - left);
                    if (gap >= (long)_timeout.TotalMilliseconds)
                    {
                        EmitSessionEnd(left, "timeout", true);
                        BeginSession(now, coldStart: false);
                        Emit(AppForeground, _current, now, new Dictionary<string, object> { { "paused_ms", gap }, { "new_session", true } });
                    }
                    else
                    {
                        _foregroundSince = now; _backgroundAt = 0; _aliveAt = now;
                        Emit(AppForeground, _current, now, new Dictionary<string, object> { { "paused_ms", gap }, { "new_session", false } });
                    }
                }
                _version++;
            }
        }

        /// <summary>The application is quitting: the session ends now (or at the moment the player left, if they already had).</summary>
        internal void OnQuit()
        {
            lock (_sync)
            {
                if (_current == null || _ended) return;
                var now = _nowMs();
                if (_backgroundAt != 0) EmitSessionEnd(_backgroundAt, "quit", true);
                else { _activeMs += Math.Max(0, now - _foregroundSince); _foregroundSince = 0; EmitSessionEnd(now, "quit", false); }
                _version++;
            }
        }

        /// <summary>Proof of life, called every few seconds while the player is in the game; what a later launch uses as the end of a session whose process vanished.</summary>
        internal void Touch()
        {
            lock (_sync)
            {
                if (_current == null || _ended || _backgroundAt != 0) return;
                _aliveAt = _nowMs();
                _version++;
            }
        }

        /// <summary>The small document persisted so a later launch can close this session if the process dies (one JSON object).</summary>
        internal string Snapshot()
        {
            lock (_sync)
            {
                if (_current == null) return "";
                var json = new StringBuilder(160);
                json.Append("{\"v\":").Append(StateVersionNumber).Append(",\"id\":\"").Append(_current.Id.ToString("D")).Append("\",\"start\":").Append(_current.StartUnixMs.ToString(CultureInfo.InvariantCulture))
                    .Append(",\"alive\":").Append(_aliveAt.ToString(CultureInfo.InvariantCulture)).Append(",\"active\":").Append(_activeMs.ToString(CultureInfo.InvariantCulture))
                    .Append(",\"fg\":").Append(_foregroundSince.ToString(CultureInfo.InvariantCulture)).Append(",\"bg\":").Append(_backgroundAt.ToString(CultureInfo.InvariantCulture))
                    .Append(",\"ended\":").Append(_ended ? 1 : 0).Append('}');
                return json.ToString();
            }
        }

        /// <summary>
        /// Closes the session of a previous process that left no <c>sys_session_end</c>. <paramref name="previousState"/> is the last saved
        /// <see cref="Snapshot"/>; <paramref name="exitInfoJson"/> is the platform's account of how that process died (Android ApplicationExitInfo), or empty.
        /// </summary>
        internal void Recover(string previousState, string exitInfoJson)
        {
            if (string.IsNullOrEmpty(previousState)) return;
            Dictionary<string, object> state;
            try { state = MiniJson.ParseObject(previousState); } catch (FormatException) { return; }
            if (Number(state, "ended") == 1 || !Guid.TryParse(state.TryGetValue("id", out var idValue) ? idValue as string : null, out var id)) return;
            var start = Number(state, "start"); var alive = Number(state, "alive"); var active = Number(state, "active");
            var foregroundSince = Number(state, "fg"); var backgroundAt = Number(state, "bg");

            long exitTimestamp = 0; var exitName = "";
            if (!string.IsNullOrEmpty(exitInfoJson))
            {
                try
                {
                    var exit = MiniJson.ParseObject(exitInfoJson);
                    var timestamp = Number(exit, "timestamp");
                    if (timestamp >= start) { exitTimestamp = timestamp; exitName = ExitReasonName((int)Number(exit, "reason")); }
                }
                catch (FormatException) { }
            }

            long end; string reason; bool background;
            if (backgroundAt != 0)
            {
                // The player had already left; the process was merely killed later. The session ended when they left.
                end = backgroundAt; reason = "background_killed"; background = true;
            }
            else
            {
                background = false;
                end = exitTimestamp != 0 ? Math.Max(alive, exitTimestamp) : alive;
                if (foregroundSince != 0) active += Math.Max(0, Math.Min(end, alive + 60000) - foregroundSince);
                reason = exitName.Length > 0 ? exitName : "unknown_kill";
            }
            lock (_sync)
            {
                Emit(SessionEnd, new SessionInfo(id, start), end, new Dictionary<string, object>
                {
                    { "duration_ms", Math.Max(0, end - start) }, { "active_ms", Math.Max(0, active) }, { "reason", reason }, { "background", background },
                });
            }
        }

        internal static string ExitReasonName(int reason)
        {
            switch (reason)
            {
                case 1: return "exit_self";
                case 2: return "signaled";
                case 3: return "low_memory";
                case 4: return "crash";
                case 5: return "native_crash";
                case 6: return "anr";
                case 7: return "init_failure";
                case 8: return "permission_change";
                case 9: return "excessive_resource_usage";
                case 10: return "user_requested";
                case 11: return "user_stopped";
                case 12: return "dependency_died";
                case 13: return "other";
                case 14: return "frozen";
                case 15: return "package_state_change";
                case 16: return "package_updated";
                default: return "unknown";
            }
        }

        // --- internals (callers hold the lock) -----------------------------------------------------------

        private void BeginSession(long now, bool coldStart)
        {
            var info = new SessionInfo(_newId(), now);
            System.Threading.Volatile.Write(ref _current, info);
            _activeMs = 0; _foregroundSince = now; _backgroundAt = 0; _aliveAt = now; _ended = false;
            Emit(SessionStart, info, now, new Dictionary<string, object> { { "cold_start", coldStart } });
            _version++;
        }

        private void EmitSessionEnd(long endAt, string reason, bool background)
        {
            Emit(SessionEnd, _current, endAt, new Dictionary<string, object>
            {
                { "duration_ms", Math.Max(0, endAt - _current.StartUnixMs) }, { "active_ms", _activeMs }, { "reason", reason }, { "background", background },
            });
            _ended = true;
        }

        private void Emit(string name, SessionInfo session, long at, Dictionary<string, object> properties) =>
            _sink.Emit(name, session.Id, at, Math.Max(0, at - session.StartUnixMs), properties);

        private static long Number(Dictionary<string, object> map, string key) =>
            map.TryGetValue(key, out var value) && value is JsonNumber number && long.TryParse(number.Lexeme, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var result) ? result : 0;
    }
}
