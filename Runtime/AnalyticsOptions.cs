using System;

namespace Daliys.Analytics
{
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
        public TimeSpan UploadInterval { get; set; } = TimeSpan.FromSeconds(30);
        public int UploadEventThreshold { get; set; } = 50;
        public int DurableEventLimit { get; set; } = 10000;
        public long DurableByteLimit { get; set; } = 20L * 1024L * 1024L;
        public TimeSpan MaxEventAge { get; set; } = TimeSpan.FromDays(7);
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

            if (DurableEventLimit <= 0 || DurableByteLimit <= 0 || MaxEventAge <= TimeSpan.Zero)
                throw new ArgumentOutOfRangeException("Durable queue limits must be positive.");

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
