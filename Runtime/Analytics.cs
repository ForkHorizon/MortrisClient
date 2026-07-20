using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Daliys.Analytics.Internal;

namespace Daliys.Analytics
{
    public static class Analytics
    {
        private static AnalyticsRuntime _runtime;

        public static void Initialize(AnalyticsOptions options)
        {
            if (options == null)
                throw new ArgumentNullException(nameof(options));

            options.Validate();
            var existing = Volatile.Read(ref _runtime);
            if (existing != null)
            {
                if (!existing.HasSameEndpointAs(options))
                    throw new InvalidOperationException("Analytics is already initialized with a different endpoint configuration.");

                return;
            }

            var created = new AnalyticsRuntime(options);
            if (Interlocked.CompareExchange(ref _runtime, created, null) != null &&
                !Volatile.Read(ref _runtime).HasSameEndpointAs(options))
            {
                throw new InvalidOperationException("Analytics is already initialized with a different endpoint configuration.");
            }
        }

        public static TrackResult Track(string eventName, IReadOnlyDictionary<string, object> properties = null)
        {
            var runtime = Volatile.Read(ref _runtime);
            return runtime == null ? TrackResult.NotInitialized : runtime.Track(eventName, properties);
        }

        public static Task<FlushResult> FlushAsync(CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var runtime = Volatile.Read(ref _runtime);
            return runtime == null
                ? Task.FromResult(new FlushResult(FlushStatus.NotInitialized, 0))
                : runtime.FlushAsync(cancellationToken);
        }

        public static void SetCollectionEnabled(bool enabled, bool clearPendingWhenDisabled = true)
        {
            Volatile.Read(ref _runtime)?.SetCollectionEnabled(enabled, clearPendingWhenDisabled);
        }

        public static AnalyticsDiagnostics GetDiagnostics()
        {
            var runtime = Volatile.Read(ref _runtime);
            return runtime == null
                ? new AnalyticsDiagnostics(false, false, 0, 0, 0)
                : runtime.GetDiagnostics();
        }

        internal static void ResetForTests()
        {
            Interlocked.Exchange(ref _runtime, null)?.Dispose();
        }
    }
}
