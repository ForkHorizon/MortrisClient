using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Daliys.Analytics.Internal.Session;
using Daliys.Analytics.Internal.Transport;

namespace Daliys.Analytics.Internal
{
    internal sealed class AnalyticsRuntime : ISessionEventSink
    {
        private readonly AnalyticsOptions _options;
        private readonly AnalyticsPersistenceWorker _persistenceWorker;
        private readonly SessionTracker _session;
        private int _localCollectionEnabled = 1;
        private int _serverCollectionEnabled = 1;
        private long _handoffDropNewest;
        private long _invalidEvents;
        private readonly EventRateLimiter _limiter;

        internal AnalyticsRuntime(AnalyticsOptions options)
        {
            _options = options;
            _limiter = new EventRateLimiter(options.MaxEventsPerSecondPerName);
            _persistenceWorker = new AnalyticsPersistenceWorker(options, ApplyServerPolicy);
            _session = new SessionTracker(NowMs, options.SessionTimeout, this);
            _persistenceWorker.AttachSession(_session);
            _session.Start();
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

            if (!_limiter.TryAcquire(eventName))
                return TrackResult.RateLimited;

            var session = _session.Current;
            var now = NowMs();
            try
            {
                return Write(eventName, properties, session.Id, now, now - session.StartUnixMs, false)
                    ? TrackResult.AcceptedToHandoff
                    : CountDropped();
            }
            catch (InvalidOperationException)
            {
                // the caller changed the dictionary while it was being read
                Interlocked.Increment(ref _invalidEvents);
                return TrackResult.InvalidProperties;
            }
        }

        private TrackResult CountDropped()
        {
            Interlocked.Increment(ref _handoffDropNewest);
            return TrackResult.HandoffFull;
        }

        /// <summary>A session ends once, so its end event has a fixed id: a recovery repeated after a crash is stored once (the queue ignores a known id).</summary>
        private static Guid SessionEndId(Guid sessionId)
        {
            var bytes = sessionId.ToByteArray();
            for (var i = 0; i < bytes.Length; i++) bytes[i] ^= 0xA5;
            bytes[7] = (byte)((bytes[7] & 0x0F) | 0x40); bytes[8] = (byte)((bytes[8] & 0x3F) | 0x80); // still a version-4 UUID: the servers validate it
            return new Guid(bytes);
        }

        /// <summary>Encodes the event once into its binary record and hands it to the buffer.</summary>
        private bool Write(string name, IReadOnlyDictionary<string, object> properties, Guid sessionId, long occurredAtUnixMs, long sessionElapsedMs, bool priority)
        {
            var writer = EventRecordWriter.ForThread;
            writer.Begin(name == "sys_session_end" ? SessionEndId(sessionId) : Guid.NewGuid(), sessionId, occurredAtUnixMs, sessionElapsedMs, _persistenceWorker.ContextBytes, name, properties == null ? 0 : properties.Count);
            if (properties is Dictionary<string, object> map)
            {
                foreach (var property in map)
                    writer.AddClr(property.Key, property.Value);
            }
            else if (properties != null)
            {
                foreach (var property in properties)
                    writer.AddClr(property.Key, property.Value);
            }
            var length = writer.Finish();
            return _persistenceWorker.TryEnqueue(writer.Buffer, length, priority);
        }

        /// <summary>A lifecycle event (session start/end, background/foreground): stamped with the session and moment the tracker names, never dropped for want of room.</summary>
        void ISessionEventSink.Emit(string name, Guid sessionId, long occurredAtUnixMs, long sessionElapsedMs, IReadOnlyDictionary<string, object> properties)
        {
            if (!IsCollectionEnabled)
                return;
            try { Write(name, properties, sessionId, occurredAtUnixMs, sessionElapsedMs, true); }
            catch (InvalidOperationException) { Interlocked.Increment(ref _invalidEvents); }
        }

        internal void SetEventRateLimit(string eventName, int perSecond) => _limiter.SetLimit(eventName, perSecond);

        internal void SetCollectionEnabled(bool enabled, bool clearPendingWhenDisabled)
        {
            Interlocked.Exchange(ref _localCollectionEnabled, enabled ? 1 : 0);
            if (!enabled && clearPendingWhenDisabled)
                _persistenceWorker.ClearPending();
        }

        internal Task<FlushResult> FlushAsync(CancellationToken cancellationToken) =>
            _persistenceWorker.FlushAsync(cancellationToken);

        // --- game lifecycle (called by AnalyticsLifecycle on the Unity main thread) -------------------------

        /// <summary>The player left (true) or came back (false). Leaving writes everything to the durable queue before returning.</summary>
        internal void OnApplicationPause(bool paused)
        {
            _session.OnPause(paused);
            if (paused && _persistenceWorker.PersistNow())
                _persistenceWorker.RequestBackgroundUpload();
        }

        internal void OnApplicationFocus(bool hasFocus)
        {
            if (!hasFocus)
                _persistenceWorker.PersistNow();
        }

        internal void OnApplicationQuit()
        {
            _session.OnQuit();
            if (_persistenceWorker.PersistNow())
                _persistenceWorker.RequestBackgroundUpload();
        }

        internal AnalyticsDiagnostics GetDiagnostics()
        {
            return new AnalyticsDiagnostics(
                initialized: true,
                collectionEnabled: IsCollectionEnabled,
                handoffCount: _persistenceWorker.HandoffCount,
                handoffDropNewest: Interlocked.Read(ref _handoffDropNewest),
                invalidEvents: Interlocked.Read(ref _invalidEvents),
                rateLimited: _limiter.Limited);
        }

        internal void Dispose() => _persistenceWorker.Dispose();

        private static long NowMs() => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

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
    }
}
