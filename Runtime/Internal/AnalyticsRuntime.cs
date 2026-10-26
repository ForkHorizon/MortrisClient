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
        private readonly bool _typedNumbers;

        internal AnalyticsRuntime(AnalyticsOptions options)
        {
            _options = options;
            var pi = AnalyticsProf.Begin();
            _limiter = new EventRateLimiter(options.MaxEventsPerSecondPerName);
            AnalyticsProf.End(Stage.InitLimiter, pi);
            _typedNumbers = options.UseTransportV8;
            pi = AnalyticsProf.Begin();
            _persistenceWorker = new AnalyticsPersistenceWorker(options, ApplyServerPolicy);
            AnalyticsProf.End(Stage.InitWorker, pi);
            pi = AnalyticsProf.Begin();
            _session = new SessionTracker(NowMs, options.SessionTimeout, this);
            AnalyticsProf.End(Stage.InitSessionTracker, pi);
            _persistenceWorker.AttachSession(_session);
            pi = AnalyticsProf.Begin();
            _session.Start();
            AnalyticsProf.End(Stage.InitSessionStart, pi);
        }

        internal bool HasSameEndpointAs(AnalyticsOptions options) => _options.HasSameEndpointAs(options);

        internal TrackResult Track(string eventName, IReadOnlyDictionary<string, object> properties)
        {
            var tt = AnalyticsProf.Begin();
            try { return TrackCore(eventName, properties); } finally { AnalyticsProf.End(Stage.TrackTotal, tt); AnalyticsProf.Count(AnalyticsProf.Counter.Events); }
        }

        private TrackResult TrackCore(string eventName, IReadOnlyDictionary<string, object> properties)
        {
            if (!IsCollectionEnabled)
                return TrackResult.CollectionDisabled;

            var tv = AnalyticsProf.Begin();
            var nameOk = EventValidator.IsValidPublicEventName(eventName);
            var propertiesOk = nameOk && EventValidator.HasValidProperties(properties);
            AnalyticsProf.End(Stage.TrackValidate, tv);
            if (!nameOk)
            {
                Interlocked.Increment(ref _invalidEvents);
                return TrackResult.InvalidEventName;
            }

            if (!propertiesOk)
            {
                Interlocked.Increment(ref _invalidEvents);
                return TrackResult.InvalidProperties;
            }

            var tl = AnalyticsProf.Begin();
            var allowed = _limiter.TryAcquire(eventName);
            AnalyticsProf.End(Stage.TrackLimiter, tl);
            if (!allowed)
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
            var te = AnalyticsProf.Begin();
            var length = Encode(writer, name, properties, sessionId, occurredAtUnixMs, sessionElapsedMs);
            AnalyticsProf.End(Stage.TrackEncode, te);
            return _persistenceWorker.TryEnqueue(writer.Buffer, length, priority);
        }

        private int Encode(EventRecordWriter writer, string name, IReadOnlyDictionary<string, object> properties, Guid sessionId, long occurredAtUnixMs, long sessionElapsedMs)
        {
            writer.TypedNumbers = _typedNumbers;
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
            return writer.Finish();
        }

        /// <summary>
        /// Encodes the events on a pool thread and writes them to the durable queue in chunks, without touching the in-memory buffer or the calling frame. Events keep the
        /// time they carry (the moment of the call when they carry none). The collection and the property dictionaries must stay unchanged until the task completes.
        /// </summary>
        internal Task<BatchResult> TrackBatchAsync(IReadOnlyList<BatchEvent> events, CancellationToken cancellationToken)
        {
            if (!IsCollectionEnabled)
                return Task.FromResult(new BatchResult(events.Count, 0, 0, 0, true, collectionDisabled: true));
            var session = _session.Current;
            var callTime = NowMs();
            return Task.Run(() =>
            {
                const int ChunkEvents = 500, ChunkBytes = 1024 * 1024;
                var writer = new EventRecordWriter { TypedNumbers = _typedNumbers };
                var frame = new System.IO.MemoryStream();
                int accepted = 0, invalid = 0, inChunk = 0, lost = 0; var completed = true;
                bool Flush()
                {
                    if (inChunk == 0) return true;
                    var tbw = AnalyticsProf.Begin();
                    var ok = _persistenceWorker.WriteFramesDirect(frame.ToArray(), inChunk);
                    AnalyticsProf.End(Stage.BatchWrite, tbw);
                    if (ok) accepted += inChunk; else lost += inChunk;
                    frame.SetLength(0); inChunk = 0;
                    return ok;
                }
                for (var i = 0; i < events.Count; i++)
                {
                    if (cancellationToken.IsCancellationRequested) { completed = false; break; }
                    var item = events[i];
                    if (!EventValidator.IsValidPublicEventName(item.Name) || !EventValidator.HasValidProperties(item.Properties)) { invalid++; Interlocked.Increment(ref _invalidEvents); continue; }
                    var at = item.Time.HasValue ? item.Time.Value.ToUnixTimeMilliseconds() : callTime;
                    int length;
                    var tbe = AnalyticsProf.Begin();
                    try { length = Encode(writer, item.Name, item.Properties, session.Id, at, Math.Max(0, at - session.StartUnixMs)); AnalyticsProf.End(Stage.BatchEncode, tbe); }
                    catch (InvalidOperationException) { invalid++; Interlocked.Increment(ref _invalidEvents); continue; }
                    frame.WriteByte((byte)(length >> 24)); frame.WriteByte((byte)(length >> 16)); frame.WriteByte((byte)(length >> 8)); frame.WriteByte((byte)length);
                    frame.Write(writer.Buffer, 0, length);
                    inChunk++;
                    if (inChunk >= ChunkEvents || frame.Length >= ChunkBytes) Flush();
                }
                Flush();
                _persistenceWorker.WakeUp();
                return new BatchResult(events.Count, accepted, invalid, lost, completed);
            }, cancellationToken);
        }

        /// <summary>A lifecycle event (session start/end, background/foreground): stamped with the session and moment the tracker names, never dropped for want of room.</summary>
        void ISessionEventSink.Emit(string name, Guid sessionId, long occurredAtUnixMs, long sessionElapsedMs, IReadOnlyDictionary<string, object> properties)
        {
            if (!IsCollectionEnabled)
                return;
            try { Write(name, properties, sessionId, occurredAtUnixMs, sessionElapsedMs, true); }
            catch (InvalidOperationException) { Interlocked.Increment(ref _invalidEvents); }
        }

        internal void SetNetworkReachable(bool reachable) => _persistenceWorker.SetNetworkReachable(reachable);

        internal long NextId(string counter) => _persistenceWorker.NextId(counter);

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
            var tp = AnalyticsProf.Begin();
            _session.OnPause(paused);
            if (paused && _persistenceWorker.PersistNow())
                _persistenceWorker.RequestBackgroundUpload();
            else if (!paused)
                _persistenceWorker.OnForeground();
            AnalyticsProf.End(Stage.PauseTotal, tp);
        }

        internal void OnApplicationFocus(bool hasFocus)
        {
            if (!hasFocus)
                _persistenceWorker.PersistNow();
            else
                _persistenceWorker.OnForeground();
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
                rateLimited: _limiter.Limited,
                queueEvictedEvents: _persistenceWorker.QueueEvicted,
                bufferFlushedByTrack: _persistenceWorker.BufferFlushedByTrack);
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
