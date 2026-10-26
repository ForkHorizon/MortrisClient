using System;

namespace Daliys.Analytics
{
    /// <summary>
    /// Ready-made trade-offs between how soon events reach the server and how much traffic and battery they cost (measured on the project's real events:
    /// see Documentation/V8Transport.md). Realtime sends every 5 seconds or 20 events and costs the most traffic per event; Standard every 2 minutes or 200 events;
    /// TrafficSaver every 5 minutes or 500 events, with the fewest requests and connections.
    /// </summary>
    public enum AnalyticsProfile { Standard, Realtime, TrafficSaver }

    public sealed class AnalyticsOptions
    {
        public string ServerUrl { get; set; }
        public string ProjectId { get; set; }
        public string Environment { get; set; }
        public string AppVersion { get; set; }
        public string BuildNumber { get; set; }
        public bool DebugLogging { get; set; }
        /// <summary>
        /// Opt in to the V7 binary transport (sequence streams, catalog + dictionary, zstd). The SDK asks the server whether the
        /// project supports it and silently keeps using V1 batches when it does not, or when the native library is unavailable.
        /// </summary>
        public bool UseTransportV7 { get; set; }
        /// <summary>
        /// Opt in to the V8 binary transport (short server-issued installation id, token, shapes registered by the SDK, per-project dictionary). It replaces V7 and
        /// falls back to V1 the same way. Events keep the type of their numbers (a float stays a float whatever its value). See Theory~/transport-v8.
        /// </summary>
        public bool UseTransportV8 { get; set; }
        /// <summary>How often the queue is uploaded. Fewer, fuller packets cost fewer bytes and less battery; events wait at most about this long.</summary>
        public TimeSpan UploadInterval { get; set; } = TimeSpan.FromSeconds(120);
        /// <summary>Queued events that start an upload before the interval is up.</summary>
        public int UploadEventThreshold { get; set; } = 200;
        /// <summary>Most events in one packet (V7 allows up to 500; the V1 fallback never sends more than 100 per request).</summary>
        public int MaxPacketEvents { get; set; } = 200;
        /// <summary>Most events of one name per second (a burst of that size is allowed); 0 = no limit. Refused events return <see cref="TrackResult.RateLimited"/>.</summary>
        public int MaxEventsPerSecondPerName { get; set; }
        /// <summary>When the game goes to the background or quits, try one short upload of what is queued instead of waiting for the next interval.</summary>
        public bool UploadOnBackground { get; set; } = true;
        /// <summary>Least time between two such background uploads (quick app switching must not cause a string of requests).</summary>
        public TimeSpan BackgroundUploadMinGap { get; set; } = TimeSpan.FromSeconds(30);
        /// <summary>The background upload gives up after this long; the events stay queued.</summary>
        public TimeSpan BackgroundUploadTimeout { get; set; } = TimeSpan.FromSeconds(10);
        /// <summary>
        /// Most events the on-device queue keeps while they wait for the server; 0 = no limit by count (the default: the size of an event varies a lot, so
        /// <see cref="DurableByteLimit"/> is the limit that matters).
        /// </summary>
        public int DurableEventLimit { get; set; }
        /// <summary>
        /// Most bytes the on-device queue occupies (events plus about 40 bytes of bookkeeping each). When it is full the OLDEST events are dropped to make room, and the
        /// drop is counted (<see cref="AnalyticsDiagnostics.QueueEvictedEvents"/>) and reported to the server. 64 MB holds roughly 80 000 events of an ordinary game
        /// (a player offline for four hours produces about 12 000); raise it if the game sends many events and players stay offline for days.
        /// </summary>
        public long DurableByteLimit { get; set; } = 64L * 1024L * 1024L;
        /// <summary>
        /// How long an event may wait in the queue before it is discarded; <see cref="TimeSpan.Zero"/> = never (the default): a player who comes back after two weeks
        /// still delivers what happened, and the server recomputes statistics for late events. Only <see cref="DurableByteLimit"/> bounds the queue then.
        /// </summary>
        public TimeSpan MaxEventAge { get; set; } = TimeSpan.Zero;
        /// <summary>
        /// Most events in one packet while the queue holds a backlog (a player was offline, or the game exported many events at once): bigger packets cost fewer bytes
        /// and fewer requests. V8 allows up to 500. <see cref="MaxPacketEvents"/> applies when only a few events wait.
        /// </summary>
        public int BacklogPacketEvents { get; set; } = 500;
        /// <summary>Pause between two packets of a backlog upload, so draining a large queue does not compete with the game for the network and the CPU. <see cref="TimeSpan.Zero"/> = none.</summary>
        public TimeSpan BacklogPacketPause { get; set; } = TimeSpan.FromMilliseconds(300);
        /// <summary>
        /// Size the packets by what the network manages: after a failed or slow request the next packets are smaller, after fast ones they grow back toward
        /// <see cref="MaxPacketEvents"/> / <see cref="BacklogPacketEvents"/>. Needs no permission (it only looks at the time the requests took).
        /// </summary>
        public bool AdaptivePacketSize { get; set; } = true;
        /// <summary>
        /// Most memory the events may use between <c>Track()</c> and the queue write (they wait one <see cref="EventBufferWindow"/>). When a burst fills it, <c>Track()</c> writes the
        /// buffer to the queue itself and goes on: nothing is lost, the calling frame is just longer. Use <c>Analytics.TrackBatchAsync</c> to export many events without that.
        /// </summary>
        public int EventBufferBytes { get; set; } = 2 * 1024 * 1024;
        /// <summary>
        /// How long tracked events wait in memory before they are written to the durable queue in one batch. Longer windows cost less CPU; at most this much
        /// is lost if the process is killed without warning. Leaving the game (pause, quit) always writes immediately. <see cref="TimeSpan.Zero"/> writes every event at once.
        /// </summary>
        public TimeSpan EventBufferWindow { get; set; } = TimeSpan.FromMilliseconds(200);
        /// <summary>
        /// How long the player may stay out of the game (app in the background) before their session counts as over: coming back later starts a new session,
        /// and the old one ends at the moment they left.
        /// </summary>
        public TimeSpan SessionTimeout { get; set; } = TimeSpan.FromMinutes(5);

        /// <summary>Sets the three upload settings that trade delay against traffic (see <see cref="AnalyticsProfile"/>); other options stay as they are.</summary>
        public AnalyticsOptions UseProfile(AnalyticsProfile profile)
        {
            switch (profile)
            {
                case AnalyticsProfile.Realtime: UploadInterval = TimeSpan.FromSeconds(5); UploadEventThreshold = 20; MaxPacketEvents = 200; break;
                case AnalyticsProfile.TrafficSaver: UploadInterval = TimeSpan.FromMinutes(5); UploadEventThreshold = 500; MaxPacketEvents = 500; break;
                default: UploadInterval = TimeSpan.FromSeconds(120); UploadEventThreshold = 200; MaxPacketEvents = 200; break;
            }
            return this;
        }

        internal void Validate()
        {
            if (string.IsNullOrWhiteSpace(ServerUrl) ||
                !Uri.TryCreate(ServerUrl, UriKind.Absolute, out var serverUri) ||
                (serverUri.Scheme != Uri.UriSchemeHttps && !IsLoopbackDevelopmentHttp(serverUri)))
            {
                throw new ArgumentException("ServerUrl must be an absolute HTTPS URL.", nameof(ServerUrl));
            }

            if (string.IsNullOrWhiteSpace(ProjectId))
                throw new ArgumentException("ProjectId is required.", nameof(ProjectId));

            if (string.IsNullOrWhiteSpace(Environment))
                throw new ArgumentException("Environment is required.", nameof(Environment));

            if (UploadInterval <= TimeSpan.Zero)
                throw new ArgumentOutOfRangeException(nameof(UploadInterval));

            if (UploadEventThreshold <= 0)
                throw new ArgumentOutOfRangeException(nameof(UploadEventThreshold));

            if (MaxEventsPerSecondPerName < 0)
                throw new ArgumentOutOfRangeException(nameof(MaxEventsPerSecondPerName));

            if (MaxPacketEvents < 1 || MaxPacketEvents > 500)
                throw new ArgumentOutOfRangeException(nameof(MaxPacketEvents));

            if (BackgroundUploadMinGap < TimeSpan.Zero || BackgroundUploadTimeout <= TimeSpan.Zero)
                throw new ArgumentOutOfRangeException(nameof(BackgroundUploadTimeout));

            if (DurableEventLimit < 0 || DurableByteLimit <= 0 || MaxEventAge < TimeSpan.Zero)
                throw new ArgumentOutOfRangeException("Durable queue limits must not be negative (0 = no limit by count / no expiry) and the byte limit must be positive.");

            if (BacklogPacketEvents < 1 || BacklogPacketEvents > 500)
                throw new ArgumentOutOfRangeException(nameof(BacklogPacketEvents));

            if (BacklogPacketPause < TimeSpan.Zero || BacklogPacketPause > TimeSpan.FromSeconds(10))
                throw new ArgumentOutOfRangeException(nameof(BacklogPacketPause));

            if (EventBufferBytes < 64 * 1024 || EventBufferBytes > 64 * 1024 * 1024)
                throw new ArgumentOutOfRangeException(nameof(EventBufferBytes));

            if (EventBufferWindow < TimeSpan.Zero || EventBufferWindow > TimeSpan.FromSeconds(5))
                throw new ArgumentOutOfRangeException(nameof(EventBufferWindow));

            if (SessionTimeout <= TimeSpan.Zero)
                throw new ArgumentOutOfRangeException(nameof(SessionTimeout));
        }

        /// <summary>Plain HTTP is accepted only for the development host itself (loopback or the Android emulator's host alias), never a routable address.</summary>
        private static bool IsLoopbackDevelopmentHttp(Uri uri) =>
            uri.Scheme == Uri.UriSchemeHttp && (uri.IsLoopback || uri.Host == "10.0.2.2");

        internal bool HasSameEndpointAs(AnalyticsOptions other)
        {
            return other != null &&
                   string.Equals(ServerUrl, other.ServerUrl, StringComparison.Ordinal) &&
                   string.Equals(ProjectId, other.ProjectId, StringComparison.Ordinal) &&
                   string.Equals(Environment, other.Environment, StringComparison.Ordinal);
        }
    }
}
