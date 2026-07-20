using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;

namespace Daliys.Analytics.Internal
{
    internal sealed class AnalyticsRuntime
    {
        internal const int HandoffCapacity = 256;

        private readonly AnalyticsOptions _options;
        private readonly AnalyticsPersistenceWorker _persistenceWorker;
        private readonly Stopwatch _sessionStopwatch = Stopwatch.StartNew();
        private readonly string _sessionId = Guid.NewGuid().ToString("D");
        private int _localCollectionEnabled = 1;
        private int _serverCollectionEnabled = 1;
        private long _handoffDropNewest;
        private long _invalidEvents;

        internal AnalyticsRuntime(AnalyticsOptions options)
        {
            _options = options;
            _persistenceWorker = new AnalyticsPersistenceWorker(options, ApplyServerPolicy);
        }

        internal bool HasSameEndpointAs(AnalyticsOptions options) => _options.HasSameEndpointAs(options);

        internal TrackResult Track(string eventName, IReadOnlyDictionary<string, object> properties)
        {
            if (!IsCollectionEnabled)
                return TrackResult.CollectionDisabled;

            if (!EventValidator.IsValidPublicEventName(eventName))
            {
                Interlocked.Increment(ref _invalidEvents);
                return TrackResult.InvalidEventName;
            }

            if (!EventValidator.HasValidProperties(properties))
            {
                Interlocked.Increment(ref _invalidEvents);
                return TrackResult.InvalidProperties;
            }

            var trackedEvent = new TrackedEvent(
                Guid.NewGuid().ToString("D"),
                _sessionId,
                eventName,
                CopyProperties(properties),
                DateTimeOffset.UtcNow,
                _sessionStopwatch.ElapsedMilliseconds);
            if (!_persistenceWorker.TryEnqueue(trackedEvent))
            {
                Interlocked.Increment(ref _handoffDropNewest);
                return TrackResult.HandoffFull;
            }
            return TrackResult.AcceptedToHandoff;
        }

        internal void SetCollectionEnabled(bool enabled, bool clearPendingWhenDisabled)
        {
            Interlocked.Exchange(ref _localCollectionEnabled, enabled ? 1 : 0);
            if (!enabled && clearPendingWhenDisabled)
                _persistenceWorker.ClearPending();
        }

        internal Task<FlushResult> FlushAsync(CancellationToken cancellationToken) =>
            _persistenceWorker.FlushAsync(cancellationToken);

        internal AnalyticsDiagnostics GetDiagnostics()
        {
            return new AnalyticsDiagnostics(
                initialized: true,
                collectionEnabled: IsCollectionEnabled,
                handoffCount: _persistenceWorker.HandoffCount,
                handoffDropNewest: Interlocked.Read(ref _handoffDropNewest),
                invalidEvents: Interlocked.Read(ref _invalidEvents));
        }

        internal void Dispose() => _persistenceWorker.Dispose();

        private void ApplyServerPolicy(ServerPolicy policy)
        {
            var collectionEnabled = policy.Mode != ServerPolicyMode.DisableCollection;
            var wasEnabled = IsCollectionEnabled;
            Interlocked.Exchange(ref _serverCollectionEnabled, collectionEnabled ? 1 : 0);
            if (wasEnabled && !IsCollectionEnabled && policy.DiscardPending)
                _persistenceWorker.ClearPending();
        }

        private bool IsCollectionEnabled =>
            Volatile.Read(ref _localCollectionEnabled) == 1 && Volatile.Read(ref _serverCollectionEnabled) == 1;

        private static IReadOnlyDictionary<string, object> CopyProperties(IReadOnlyDictionary<string, object> properties)
        {
            if (properties == null || properties.Count == 0)
                return new ReadOnlyDictionary<string, object>(new Dictionary<string, object>());

            var copy = new Dictionary<string, object>(properties.Count, StringComparer.Ordinal);
            foreach (var property in properties)
                copy.Add(property.Key, property.Value);

            return new ReadOnlyDictionary<string, object>(copy);
        }

        internal sealed class TrackedEvent
        {
            internal TrackedEvent(string eventId, string sessionId, string name, IReadOnlyDictionary<string, object> properties, DateTimeOffset occurredAtClient, long sessionElapsedMilliseconds)
            {
                EventId = eventId;
                SessionId = sessionId;
                Name = name;
                Properties = properties;
                OccurredAtClient = occurredAtClient;
                SessionElapsedMilliseconds = sessionElapsedMilliseconds;
            }

            internal string EventId { get; }
            internal string SessionId { get; }
            internal string Name { get; }
            internal IReadOnlyDictionary<string, object> Properties { get; }
            internal DateTimeOffset OccurredAtClient { get; }
            internal long SessionElapsedMilliseconds { get; }
        }
    }
}
