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
            if (Interlocked.CompareExchange(ref _runtime, created, null) != null)
            {
                created.Dispose();
                if (!Volatile.Read(ref _runtime).HasSameEndpointAs(options))
                    throw new InvalidOperationException("Analytics is already initialized with a different endpoint configuration.");
                return;
            }

            AnalyticsLifecycle.Attach(created);
        }

        public static TrackResult Track(string eventName, IReadOnlyDictionary<string, object> properties = null)
        {
            var runtime = Volatile.Read(ref _runtime);
            return runtime == null ? TrackResult.NotInitialized : runtime.Track(eventName, properties);
        }

        /// <summary>
        /// Records many events without making the calling frame longer: they are encoded and written to the on-device queue on a background thread, in order, behind
        /// whatever <see cref="Track"/> has buffered so far. Meant for a game that exports a large number of its own events at once (a statistics dump, a replay of
        /// what happened offline); a stream of single events belongs to <see cref="Track"/>. Each event may carry the time it happened. The per-name rate limit does
        /// not apply. Do not change the list or the dictionaries until the task completes. The order of sequence numbers between a batch and <c>Track</c> calls made
        /// while it runs is not defined; event times are exact.
        /// </summary>
        public static Task<BatchResult> TrackBatchAsync(IReadOnlyList<BatchEvent> events, CancellationToken cancellationToken = default)
        {
            if (events == null)
                throw new ArgumentNullException(nameof(events));
            cancellationToken.ThrowIfCancellationRequested();
            var runtime = Volatile.Read(ref _runtime);
            return runtime == null
                ? Task.FromResult(new BatchResult(events.Count, 0, 0, events.Count, true))
                : runtime.TrackBatchAsync(events, cancellationToken);
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

        /// <summary>
        /// The next number of a named counter: 1, 2, 3... for attempts, runs, levels, anything the game wants to number. Unlike a number the game keeps in its own save
        /// data, it never goes back: the SDK stores the counter together with the events that used it, so a number the server has seen is not handed out again after a
        /// crash. Returns 0 before <see cref="Initialize"/>. A counter name is 1 to 64 characters of a-z, 0-9 and _; at most 64 counters.
        /// </summary>
        public static long NextId(string counter)
        {
            var runtime = Volatile.Read(ref _runtime);
            return runtime == null ? 0 : runtime.NextId(counter);
        }

        /// <summary>Limits one event name to <paramref name="perSecond"/> events per second (0 = back to the default from the options, negative = never limit it).</summary>
        public static void SetEventRateLimit(string eventName, int perSecond)
        {
            if (string.IsNullOrEmpty(eventName))
                throw new ArgumentNullException(nameof(eventName));
            Volatile.Read(ref _runtime)?.SetEventRateLimit(eventName, perSecond);
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
            AnalyticsLifecycle.Detach();
        }
    }
}
