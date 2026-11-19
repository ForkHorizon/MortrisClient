// The browser (WebGL) path from Track() to the server: main thread only, localStorage queue, V1 JSON over UnityWebRequest.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Daliys.Analytics.Internal.Session;
using Daliys.Analytics.Internal.Transport;
using UnityEngine;

namespace Daliys.Analytics.Internal.Web
{
    /// <summary>
    /// Sends a JSON POST (<paramref name="gzip"/>: the body is gzip and says so in Content-Encoding) and reports back later on the main thread:
    /// <c>done(status, body, retryAfter)</c>, status 0 when no response arrived (offline, CORS refused, timeout). <see cref="PostKeepalive"/> is fire-and-forget and
    /// survives the page being closed (fetch keepalive); false when it could not be started.
    /// </summary>
    internal interface IWebHttp
    {
        void Post(string url, byte[] body, bool gzip, string bearer, Action<int, string, string> done);
        bool PostKeepalive(string url, byte[] body, bool gzip, string bearer);
    }

    /// <summary>
    /// A WebGL player has no threads, no SQLite, no HttpClient and no zlib, so the browser build gets its own pipeline: events go straight into a bounded
    /// <see cref="WebEventQueue"/> (saved to localStorage every few seconds and whenever the page is hidden), and <see cref="Tick"/>, called every
    /// frame, drives one HTTP request at a time through the V1 API: register, policy, gzip batches (<see cref="WebGzip"/>). When the page is hidden the oldest events also go
    /// out once with fetch keepalive, which outlives the tab; they stay queued, so the next regular upload resends them and the server answers "duplicate".
    /// </summary>
    internal sealed class WebPipeline : IEventPipeline
    {
        /// <summary>localStorage holds about 5 MB per origin, shared with the game and, on a portal, with other games.</summary>
        internal const int StorageCharLimit = 512 * 1024; // ponytail: fixed budget (~1 100 events); an option when a game needs more offline room
        /// <summary>Most characters of event JSON in one batch: well under the 1 MiB the server inflates, and under its 256 KiB body limit even when gzip finds nothing to save.</summary>
        internal const int BatchCharLimit = 200 * 1024;
        /// <summary>Keepalive requests share a 64 KiB in-flight budget per page; stay under it with room for the envelope.</summary>
        internal const int KeepaliveByteLimit = 60 * 1024;
        /// <summary>Saving rewrites the whole queue key; leaving the page saves at once anyway, so the interval only bounds what a crash loses.</summary>
        private static readonly TimeSpan SaveInterval = TimeSpan.FromSeconds(5);
        private static readonly TimeSpan HeartbeatInterval = TimeSpan.FromSeconds(30);

        private readonly AnalyticsOptions _options;
        private readonly AnalyticsDeviceContext _device;
        private readonly IWebHttp _http;
        private readonly Func<long> _nowMs;
        private readonly Action<ServerPolicy> _policyChanged;
        private readonly WebEventQueue _queue;
        private readonly EventRecordReader _reader = new EventRecordReader();
        private readonly ParsedEvent _parsed = new ParsedEvent();
        private readonly StringBuilder _json = new StringBuilder(512);
        private readonly AnalyticsCounters _counters = new AnalyticsCounters();
        private readonly RetryBackoff _retry;
        private readonly List<TaskCompletionSource<FlushResult>> _flushWaiters = new List<TaskCompletionSource<FlushResult>>();
        private readonly string _baseUrl;
        private SessionTracker _session;
        private int _savedSessionVersion = -1;
        private bool _inFlight, _registered, _blocked, _forced, _networkReachable = true, _identityResetTried, _reregisterTried, _disposed;
        private long _nextAttemptAt, _nextUploadAt, _nextPolicyCheckAt, _nextSaveAt, _nextHeartbeatAt, _lastKeepaliveAt = long.MinValue;
        private int _batchSize;
        private ServerPolicy _policy;

        internal WebPipeline(AnalyticsOptions options, AnalyticsDeviceContext device, IWebStorage storage, IWebHttp http, Func<long> nowMs, Action<ServerPolicy> policyChanged)
        {
            _options = options; _device = device; _http = http; _nowMs = nowMs; _policyChanged = policyChanged;
            _baseUrl = options.ServerUrl.TrimEnd('/');
            var random = new System.Random();
            _retry = new RetryBackoff(TimeSpan.FromSeconds(5), TimeSpan.FromMinutes(5), random.NextDouble);
            var maxChars = (int)Math.Min(StorageCharLimit, options.DurableByteLimit);
            _queue = new WebEventQueue(storage, options.ProjectId, options.Environment, maxChars, options.DurableEventLimit);
            ContextBytes = EventContext.Build(device.TimezoneOffsetMinutes, device.AppVersion, device.BuildNumber, device.Platform, device.OSVersion, device.DeviceClass, device.Locale);
            var now = nowMs();
            _nextUploadAt = now + (long)options.UploadInterval.TotalMilliseconds;
            _nextHeartbeatAt = now + (long)HeartbeatInterval.TotalMilliseconds;
            _batchSize = Math.Min(options.MaxPacketEvents, PacketSizer.V1BatchLimit);
            _counters.Load(_queue.LoadCounters());
            // An identity the server registered on an earlier page is used as it is (a 401 sends it through registration again): registering on every page load
            // would spend the server's per-address and per-project registration allowance on page views.
            _registered = _queue.Registered;
        }

        internal WebEventQueue Queue => _queue;
        internal bool InFlight => _inFlight;
        internal bool Registered => _registered;
        internal bool Blocked => _blocked;

        public byte[] ContextBytes { get; }
        public int HandoffCount => 0; // nothing waits between Track() and the queue
        public long BufferFlushedByTrack => 0;
        public long QueueEvicted => _queue.Evicted;
        public bool MainThreadOnly => true;

        /// <summary>Connects the session tracker and closes the session a previous page left open (closed tab, reload, crash).</summary>
        public void AttachSession(SessionTracker session)
        {
            _session = session;
            session.Recover(_queue.LoadSession(), "");
        }

        public bool TryEnqueue(byte[] record, int length, bool priority = false)
        {
            if (_disposed) return false;
            try
            {
                _reader.Read(record, 0, length, _parsed);
                _json.Clear();
                EventRecordJson.Append(_json, _parsed, _parsed.EventIdText, _queue.NextSequence());
                return _queue.Add(_json.ToString());
            }
            catch (FormatException exception)
            {
                if (_options.DebugLogging) Debug.LogException(exception);
                return false;
            }
        }

        /// <summary>Records in the frame layout of <see cref="EventBuffer"/> (per record: int32 big-endian length, then the record).</summary>
        public bool WriteFramesDirect(byte[] frames, int count)
        {
            var position = 0; var ok = true;
            for (var i = 0; i < count && position + 4 <= frames.Length; i++)
            {
                var length = QueueBatch.ReadInt32(frames, ref position);
                if (length < 0 || position + length > frames.Length) return false;
                var record = new byte[length];
                Buffer.BlockCopy(frames, position, record, 0, length);
                position += length;
                ok &= TryEnqueue(record, length);
            }
            return ok;
        }

        public void WakeUp() { }

        public void SetNetworkReachable(bool reachable)
        {
            if (reachable && !_networkReachable) RequestUploadSoon();
            _networkReachable = reachable;
        }

        public long NextId(string counter) => _counters.Next(counter);

        public void ClearPending()
        {
            _queue.Clear();
            _queue.Save();
        }

        /// <summary>Saves the queue, the session and the counters to localStorage now (the page is being hidden or may close).</summary>
        public bool PersistNow()
        {
            if (_disposed) return false;
            var ok = _queue.Save();
            var counters = _counters.Snapshot();
            if (counters != null && !_queue.SaveCounters(counters)) { _counters.MarkDirty(); ok = false; }
            if (_session != null && _session.StateVersion != _savedSessionVersion)
            {
                var version = _session.StateVersion;
                if (_queue.SaveSession(_session.Snapshot())) _savedSessionVersion = version; else ok = false;
            }
            _nextSaveAt = _nowMs() + (long)SaveInterval.TotalMilliseconds;
            return ok;
        }

        /// <summary>The page is being hidden: send the oldest events once with fetch keepalive, which completes even when the tab is closed next.</summary>
        public void RequestBackgroundUpload()
        {
            var now = _nowMs();
            if (_disposed || !_options.UploadOnBackground || _blocked || !_queue.Registered || _queue.Count == 0 || UploadsPaused) return;
            if (_lastKeepaliveAt != long.MinValue && now - _lastKeepaliveAt < (long)_options.BackgroundUploadMinGap.TotalMilliseconds) return;
            // event JSON compresses several times over; the uncompressed cap keeps the server's inflate limit far away, the byte check the 64 KiB budget
            var events = _queue.Oldest(PacketSizer.V1BatchLimit, 4 * KeepaliveByteLimit);
            byte[] body = null;
            while (events.Count > 0)
            {
                body = WebGzip.Compress(BatchBody(events));
                if (body.Length <= KeepaliveByteLimit) break;
                events.RemoveRange(events.Count / 2, events.Count - events.Count / 2); // halve until the bytes fit
                body = null;
            }
            if (body != null && _http.PostKeepalive(_baseUrl + "/v1/events/batch", body, true, _queue.Credential))
                _lastKeepaliveAt = now;
        }

        /// <summary>The player came back: what is due goes out without waiting for the old back-off.</summary>
        public void OnForeground()
        {
            _retry.Reset();
            _nextAttemptAt = 0;
        }

        public Task<FlushResult> FlushAsync(CancellationToken cancellationToken)
        {
            var completion = new TaskCompletionSource<FlushResult>();
            if (_disposed) { completion.SetResult(new FlushResult(FlushStatus.PersistenceUnavailable, 0)); return completion.Task; }
            if (cancellationToken.CanBeCanceled) cancellationToken.Register(() => completion.TrySetCanceled(cancellationToken));
            _flushWaiters.Add(completion);
            _forced = true;
            return completion.Task;
        }

        public void Dispose()
        {
            if (_disposed) return;
            PersistNow();
            _disposed = true;
            CompleteFlushes(FlushStatus.PersistenceUnavailable);
        }

        // --- the clock ----------------------------------------------------------------------------------------------

        public void Tick()
        {
            if (_disposed) return;
            var now = _nowMs();
            if (now >= _nextHeartbeatAt)
            {
                _nextHeartbeatAt = now + (long)HeartbeatInterval.TotalMilliseconds;
                _session?.Touch();
                PersistNow();
            }
            else if (now >= _nextSaveAt && (_queue.Dirty || (_session != null && _session.StateVersion != _savedSessionVersion)))
            {
                PersistNow();
            }

            if (_inFlight) return;
            if (_blocked) { CompleteFlushes(FlushStatus.UploadDeferred); return; }
            if (!_forced && (now < _nextAttemptAt || !_networkReachable)) return;
            // Registration does not wait for the upload interval: most first visits to a web game are short, and only a registered identity can send its
            // events with the keepalive request when the page is hidden.
            if (!_registered) { Register(); return; }
            if (!_forced && now < _nextUploadAt && _queue.Count < _options.UploadEventThreshold) return;

            if (now >= _nextPolicyCheckAt) { FetchPolicy(); return; }
            if (UploadsPaused || _queue.Count == 0)
            {
                // disable_collection ends the round as done (nothing is to be sent), like the Android uploader; pause_upload defers it
                var paused = _policy != null && _policy.Mode == ServerPolicyMode.PauseUpload;
                RoundDone(now, paused ? FlushStatus.UploadDeferred : FlushStatus.Uploaded);
                return;
            }
            SendBatch();
        }

        private bool UploadsPaused => _policy != null && _policy.Mode != ServerPolicyMode.Active;

        private void RequestUploadSoon()
        {
            _retry.Reset();
            _nextAttemptAt = 0;
            _nextUploadAt = 0;
        }

        // --- requests -----------------------------------------------------------------------------------------------

        private void Register()
        {
            Post("/v1/installs/register", V1Client.RegisterBody(_options, _device, _queue.State), false, null, response =>
            {
                if (response.IsSuccess)
                {
                    _registered = true; _identityResetTried = false;
                    _queue.MarkRegistered();
                    ApplyPolicy(V1Client.ParseRegistrationPolicy(response.Body));
                    return;
                }
                if (response.StatusCode == 400 && response.ErrorCode == "invalid_credential" && !_identityResetTried)
                {
                    _identityResetTried = true; // a fresh identity, registered on the next tick; a second refusal falls through to the failure rules
                    _queue.ResetIdentity();
                    return;
                }
                Fail(response);
            });
        }

        private void FetchPolicy()
        {
            Post("/v1/client/policy", V1Client.PolicyBody(_options, _device, _queue.State), false, _queue.Credential, response =>
            {
                if (response.IsSuccess) { ApplyPolicy(V1Client.ParsePolicy(response.Body)); return; }
                if (response.StatusCode == 401) { _registered = false; return; } // register again on the next tick
                Fail(response);
            });
        }

        private void SendBatch()
        {
            var events = _queue.Oldest(_batchSize, BatchCharLimit);
            if (events.Count == 0) // one event bigger than a request: the server could never take it
            {
                _queue.Remove(new[] { WebEventQueue.IdOf(_queue.Oldest(1, int.MaxValue)[0]) });
                return;
            }
            var sentIds = new List<string>(events.Count);
            foreach (var e in events) sentIds.Add(WebEventQueue.IdOf(e));
            Post("/v1/events/batch", BatchBody(events), true, _queue.Credential, response =>
            {
                if (response.IsSuccess)
                {
                    var acknowledgement = V1Client.ParseAcknowledgement(response.Body, sentIds);
                    var removed = _queue.Remove(new HashSet<string>(acknowledgement.EventIds, StringComparer.Ordinal));
                    _reregisterTried = false;
                    if (removed == 0)
                    {
                        ApplyPolicy(acknowledgement.Policy);
                        BackOff(null); // the server settled none of them: resending at once would only repeat that
                        return;
                    }
                    _batchSize = Math.Min(_options.MaxPacketEvents, PacketSizer.V1BatchLimit);
                    _retry.Reset(); _nextAttemptAt = 0;
                    ApplyPolicy(acknowledgement.Policy);
                    // a full batch still waiting goes out on the next frame; anything less waits for the interval or the threshold
                    if (!_forced && _queue.Count < Math.Min(_options.MaxPacketEvents, PacketSizer.V1BatchLimit)) RoundDone(_nowMs(), FlushStatus.Uploaded);
                    return;
                }
                if (response.StatusCode == 401 && !_reregisterTried) { _reregisterTried = true; _registered = false; return; }
                if (response.StatusCode == 413)
                {
                    if (events.Count == 1) _queue.Remove(sentIds); // one event the server will never take
                    else _batchSize = Math.Max(1, events.Count / 2);
                    return;
                }
                Fail(response);
            });
        }

        private string BatchBody(List<string> events)
        {
            var array = new StringBuilder(2 + events.Count);
            array.Append('[');
            for (var i = 0; i < events.Count; i++) { if (i > 0) array.Append(','); array.Append(events[i]); }
            return V1Client.BatchBody(_options, _queue.State, array.Append(']').ToString());
        }

        private void Post(string path, string body, bool gzip, string bearer, Action<V1Client.V1Response> handle)
        {
            var bytes = gzip ? WebGzip.Compress(body) : new UTF8Encoding(false).GetBytes(body);
            _inFlight = true;
            try { _http.Post(_baseUrl + path, bytes, gzip, bearer, OnResponse); }
            catch (Exception exception) // the request could not even start (a malformed URL...): never leave the pipeline waiting for an answer that cannot come
            {
                _inFlight = false;
                if (_options.DebugLogging) Debug.LogException(exception);
                BackOff(null);
            }

            void OnResponse(int status, string text, string retryAfter)
            {
                _inFlight = false;
                if (_disposed) return;
                try
                {
                    handle(new V1Client.V1Response(status, text ?? "", V1Client.ParseRetryAfter(retryAfter, DateTimeOffset.UtcNow)));
                }
                catch (Exception exception) when (exception is InvalidDataException || exception is FormatException || exception is ArgumentException)
                {
                    if (_options.DebugLogging) Debug.LogException(exception);
                    BackOff(null); // a malformed or truncated 200 is retried like a network failure
                }
            }
        }

        /// <summary>The failure rules of the V1 contract (docs/client-integration.md): retry network, 401, 408, 429 and 5xx; stop on a conflict or any other 4xx.</summary>
        private void Fail(V1Client.V1Response response)
        {
            var status = response.StatusCode;
            if (status == 0 || status == 401 || status == 408 || status == 429 || status >= 500)
            {
                BackOff(response.RetryAfter);
                return;
            }
            // 409 install_conflict and the remaining 4xx: the queue is kept, nothing more is sent from this page (Android does the same for the process)
            _blocked = true;
            if (_options.DebugLogging) Debug.LogWarning("Mortris analytics stopped uploading: the server answered " + status + " " + response.ErrorCode);
            CompleteFlushes(FlushStatus.UploadDeferred);
        }

        private void BackOff(TimeSpan? retryAfter)
        {
            _nextAttemptAt = _nowMs() + (long)_retry.OnFailure(retryAfter).TotalMilliseconds;
            _forced = false;
            CompleteFlushes(FlushStatus.UploadDeferred);
        }

        private void RoundDone(long now, FlushStatus status)
        {
            _nextUploadAt = now + (long)_options.UploadInterval.TotalMilliseconds;
            _forced = false;
            CompleteFlushes(status);
        }

        private void ApplyPolicy(ServerPolicy policy)
        {
            _policy = policy;
            _nextPolicyCheckAt = _nowMs() + policy.NextCheckSeconds * 1000L;
            _policyChanged?.Invoke(policy);
        }

        private void CompleteFlushes(FlushStatus status)
        {
            if (_flushWaiters.Count == 0) return;
            var result = new FlushResult(status, 0);
            var waiters = _flushWaiters.ToArray();
            _flushWaiters.Clear();
            foreach (var waiter in waiters) waiter.TrySetResult(result);
        }
    }
}
