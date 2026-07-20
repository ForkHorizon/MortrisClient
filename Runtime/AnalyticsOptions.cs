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
        public TimeSpan UploadInterval { get; set; } = TimeSpan.FromSeconds(30);
        public int UploadEventThreshold { get; set; } = 50;
        public int DurableEventLimit { get; set; } = 10000;
        public long DurableByteLimit { get; set; } = 20L * 1024L * 1024L;
        public TimeSpan MaxEventAge { get; set; } = TimeSpan.FromDays(7);

        internal void Validate()
        {
            if (string.IsNullOrWhiteSpace(ServerUrl) ||
                !Uri.TryCreate(ServerUrl, UriKind.Absolute, out var serverUri) ||
                serverUri.Scheme != Uri.UriSchemeHttps)
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
        }

        internal bool HasSameEndpointAs(AnalyticsOptions other)
        {
            return other != null &&
                   string.Equals(ServerUrl, other.ServerUrl, StringComparison.Ordinal) &&
                   string.Equals(ProjectId, other.ProjectId, StringComparison.Ordinal) &&
                   string.Equals(Environment, other.Environment, StringComparison.Ordinal);
        }
    }
}
