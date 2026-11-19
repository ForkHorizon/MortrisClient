// Upload loop of the SDK: V8 packets first, V1 batches as the fallback; back-off, pacing and server policy.
using System;
using System.Threading;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using Daliys.Analytics.Internal.Transport;
using UnityEngine;

namespace Daliys.Analytics.Internal
{
    internal enum ServerPolicyMode { Active, PauseUpload, DisableCollection }

    internal sealed class ServerPolicy
    {
        internal ServerPolicy(ServerPolicyMode mode, bool discardPending, int nextCheckSeconds)
        {
            Mode = mode;
            DiscardPending = discardPending;
            NextCheckSeconds = Math.Max(300, Math.Min(86400, nextCheckSeconds));
        }

        internal ServerPolicyMode Mode { get; }
        internal bool DiscardPending { get; }
        internal int NextCheckSeconds { get; }
    }

    internal sealed class AnalyticsUploader : IDisposable
    {
        private static readonly TimeSpan InitialBackoff = TimeSpan.FromSeconds(5);
        private static readonly TimeSpan MaximumBackoff = TimeSpan.FromMinutes(5);

        private readonly AnalyticsOptions _options;
        private readonly AnalyticsDeviceContext _device;
        private readonly Action<ServerPolicy> _policyChanged;
        private readonly HttpClient _client = ProfiledClient();

        private static HttpClient ProfiledClient()
        {
            var t = AnalyticsProf.Begin();
            var client = HttpV7Transport.CreateClient();
            AnalyticsProf.End(Stage.InitHttpClient, t);
            return client;
        }
        private DateTimeOffset _nextAttemptAt;
        private DateTimeOffset _nextPolicyCheckAt;
        private DateTimeOffset _nextUploadAt;
        private static readonly System.Random SharedRandom = new System.Random();
        private readonly RetryBackoff _retry = new RetryBackoff(InitialBackoff, MaximumBackoff, () => { lock (SharedRandom) return SharedRandom.NextDouble(); });
        private PacketSizer _sizer;
        private volatile bool _networkReachable = true;
        private volatile bool _urgent;
        private bool _registered;
        private bool _installConflict;
        private bool _permanentFailure;
        private ServerPolicy _currentPolicy;
        private readonly V8Session _v8;
        private readonly V1Client _v1;
        private HttpV7Transport _http;
        /// <summary>Most events the server takes in one packet: the format's 500, lowered for good when the server says it takes fewer.</summary>
        private int _packetCap = PacketLimit;
        private const int PacketLimit = 500;
        private volatile CancellationTokenSourceBox _deadline = CancellationTokenSourceBox.None;
        private readonly EventRecordReader _reader = new EventRecordReader();

        internal AnalyticsUploader(AnalyticsOptions options, AnalyticsDeviceContext device, Action<ServerPolicy> policyChanged)
        {
            _options = options;
            _device = device;
            _policyChanged = policyChanged;
            _nextUploadAt = DateTimeOffset.UtcNow.Add(options.UploadInterval);
            _v1 = new V1Client(options, device, _client, () => _deadline.Token);
            var pi = AnalyticsProf.Begin();
            _v8 = options.UseTransportV8 ? CreateV8Session() : null;
            AnalyticsProf.End(Stage.InitV8Session, pi);
        }

        private V8Session CreateV8Session()
        {
            if (!_options.UseTransportV8) return null;
            try
            {
                // Created on the Unity main thread (the worker is constructed by Analytics.Initialize), where persistentDataPath is legal.
                var directory = Path.Combine(Application.persistentDataPath, "daliys-analytics", "v8");
                var settings = new V8Settings
                {
                    ProjectId = _options.ProjectId, SdkName = AnalyticsDeviceContext.SdkName, SdkVersion = AnalyticsDeviceContext.SdkVersion,
                    AppVersion = _device.AppVersion, BuildNumber = _device.BuildNumber, Platform = _device.Platform,
                };
                _http = new HttpV7Transport(_client, _options.ServerUrl);
                return new V8Session(settings, _http, new FileV7AssetStore(directory));
            }
            catch (Exception exception)
            {
                if (_options.DebugLogging) Debug.LogException(exception);
                return null;
            }
        }

        /// <summary>Events that make a "full" packet for the transport in use.</summary>
        private int FullPacket() => PacketSizer.FullPacket(_packetCap, _options.MaxPacketEvents, _v8 != null && !_v8.Disabled);

        /// <summary>The size of the next packet: the option while a few events wait, the backlog size while a lot waits, scaled down by what the connection managed so far.</summary>
        private int NextPacketSize(IAnalyticsQueueBridge queue)
        {
            var backlog = queue.PendingCount > 2 * _options.MaxPacketEvents;
            var ceiling = Math.Min(_packetCap, backlog ? Math.Max(_options.BacklogPacketEvents, _options.MaxPacketEvents) : _options.MaxPacketEvents);
            if (!_options.AdaptivePacketSize) return ceiling;
            return (_sizer ?? (_sizer = new PacketSizer(ceiling))).Next(ceiling);
        }

        /// <summary>The network is known to be gone (or back): while it is gone nothing is attempted unless forced. Set from the main thread.</summary>
        internal void SetNetworkReachable(bool reachable) => _networkReachable = reachable;

        /// <summary>The player returned to the game: forget the back-off so that what is due goes out at once (nothing becomes due that was not).</summary>
        internal void ForgetBackoff()
        {
            _retry.Reset();
            _nextAttemptAt = DateTimeOffset.MinValue;
        }

        /// <summary>The network came back: forget the back-off and make the next tick upload whatever waits.</summary>
        internal void RequestUploadSoon()
        {
            _urgent = true;
            _retry.Reset();
            _nextAttemptAt = DateTimeOffset.MinValue;
            _nextUploadAt = DateTimeOffset.MinValue;
        }

        internal bool NothingToDo(IAnalyticsQueueBridge queue, bool force)
        {
            var now = DateTimeOffset.UtcNow;
            if (_installConflict || _permanentFailure || (!force && (now < _nextAttemptAt || !_networkReachable)))
                return true;
            return !force && now < _nextUploadAt && queue.PendingCount < _options.UploadEventThreshold;
        }

        /// <summary>
        /// Uploads what is due. With <paramref name="deadline"/> the requests are cancelled when it passes and nothing is penalised for it (a background upload:
        /// the events simply stay queued).
        /// </summary>
        internal UploadResult Flush(IAnalyticsQueueBridge queue, bool force, TimeSpan? deadline = null)
        {
            if (deadline == null)
                return FlushCore(queue, force);

            using (var cancel = new CancellationTokenSource(deadline.Value))
            {
                var box = new CancellationTokenSourceBox(cancel.Token);
                _deadline = box;
                if (_http != null) _http.Deadline = box;
                try { return FlushCore(queue, force); }
                catch (OperationCanceledException) { return UploadResult.Deferred; }
                finally
                {
                    _deadline = CancellationTokenSourceBox.None;
                    if (_http != null) _http.Deadline = CancellationTokenSourceBox.None;
                }
            }
        }

        /// <summary>V1 registration and the periodic policy check. Returns a result when the upload must stop.</summary>
        private UploadResult PrepareV1(IAnalyticsQueueBridge queue, ref AnalyticsQueueState state, DateTimeOffset now)
        {
            if (!_registered)
            {
                var registration = _v1.RegisterWithCredentialRecovery(queue, state);
                state = registration.State;
                if (!registration.Response.IsSuccess)
                    return HandleFailure(registration.Response, now);
                _registered = true;
                return ApplyPolicy(V1Client.ParseRegistrationPolicy(registration.Response.Body));
            }

            if (now < _nextPolicyCheckAt)
                return null;

            var policy = _v1.FetchPolicy(state);
            if (policy.StatusCode == 401)
            {
                _registered = false;
                var registration = _v1.RegisterWithCredentialRecovery(queue, state);
                state = registration.State;
                if (!registration.Response.IsSuccess)
                    return HandleFailure(registration.Response, now);
                _registered = true;
                return ApplyPolicy(V1Client.ParseRegistrationPolicy(registration.Response.Body));
            }

            if (!policy.IsSuccess)
                return HandleFailure(policy, now);
            return ApplyPolicy(V1Client.ParsePolicy(policy.Body));
        }

        private UploadResult FlushCore(IAnalyticsQueueBridge queue, bool force)
        {
            var tf = AnalyticsProf.Begin();
            try { return FlushCoreInner(queue, force); } finally { AnalyticsProf.End(Stage.UploadFlush, tf); }
        }

        private UploadResult FlushCoreInner(IAnalyticsQueueBridge queue, bool force)
        {
            var now = DateTimeOffset.UtcNow;
            if (_installConflict || _permanentFailure || (!force && (now < _nextAttemptAt || !_networkReachable)))
                return UploadResult.Deferred;
            try { return Upload(queue, force, now); }
            catch (OperationCanceledException) when (!ReferenceEquals(_deadline, CancellationTokenSourceBox.None))
            {
                return UploadResult.Deferred; // the background allowance ran out: the events stay queued, no backoff
            }
            catch (Exception)
            {
                return BackOff(now, null);
            }
        }

        private bool BinaryOn => _v8 != null && !_v8.Disabled;

        private UploadResult Upload(IAnalyticsQueueBridge queue, bool force, DateTimeOffset now)
        {
            var early = BeforeUpload(queue, force, now);
            if (early != null) return early;
            var round = new UploadRound { BatchSize = NextPacketSize(queue) };
            while (true)
            {
                // Packets compress best when full: after the first one, an upload only goes on while a whole packet is waiting. The rest is sent with the
                // next due upload (or at once by FlushAsync), so a burst does not end in a string of small, expensive packets.
                if (round.Sent > 0 && !force && queue.PendingCount < FullPacket())
                {
                    ResetBackoff();
                    return UploadResult.Uploaded;
                }
                var result = SendBinary(queue, force, now, round) ?? SendV1(queue, now, round);
                if (!ReferenceEquals(result, Next)) return result;
            }
        }

        /// <summary>Whether this upload is due at all, the V1 registration and policy (when V1 is the transport) and the policy's verdict; null = go on.</summary>
        private UploadResult BeforeUpload(IAnalyticsQueueBridge queue, bool force, DateTimeOffset now)
        {
            if (_urgent)
            {
                _urgent = false;
                if (queue.PendingCount == 0) return UploadResult.Persisted;    // the trigger was only a hint: nothing waits
            }
            if (!force && now < _nextUploadAt && queue.PendingCount < _options.UploadEventThreshold)
                return UploadResult.Persisted;

            // V8 registers by itself (hello) and learns the policy from the server's version number; the V1 registration waits until a batch has to go through V1.
            if (!BinaryOn)
            {
                var state = queue.GetState();
                var tpp = AnalyticsProf.Begin();
                var preparation = PrepareV1(queue, ref state, now);
                AnalyticsProf.End(Stage.UploadPolicy, tpp);
                if (preparation != null) return preparation;
            }
            if (_currentPolicy != null && _currentPolicy.Mode == ServerPolicyMode.PauseUpload)
                return UploadResult.Deferred;
            return _currentPolicy != null && _currentPolicy.Mode == ServerPolicyMode.DisableCollection ? UploadResult.Uploaded : null;
        }

        /// <summary>One V8 packet. Returns <see cref="Next"/> to go on, a result to stop, or null when this batch goes through V1.</summary>
        private UploadResult SendBinary(IAnalyticsQueueBridge queue, bool force, DateTimeOffset now, UploadRound round)
        {
            if (!BinaryOn) return null;
            var watch = System.Diagnostics.Stopwatch.StartNew();
            var sent = _v8.Send(queue, () => queue.ReadOldest(round.BatchSize));
            watch.Stop();
            switch (sent.Kind)
            {
                case V7ResultKind.Delivered:
                    return OnPacketDelivered(queue, force, round, sent, watch.Elapsed);
                case V7ResultKind.Empty:
                    ResetBackoff();
                    return UploadResult.Uploaded;
                case V7ResultKind.Retry:
                    _sizer?.OnFailure();
                    return BackOff(now, sent.RetryAfter);
                case V7ResultKind.PayloadTooLarge:
                    if (round.BatchSize <= 1) return null; // one event that cannot fit a packet: V1 decides what to do with it
                    round.BatchSize = Math.Max(1, round.BatchSize / 2);
                    if (sent.Status == 400) _packetCap = Math.Min(_packetCap, round.BatchSize); // the server's limit on events per packet: remember it
                    return Next;
                default:
                    return null; // Fallback: this batch goes through V1
            }
        }

        private UploadResult OnPacketDelivered(IAnalyticsQueueBridge queue, bool force, UploadRound round, V7SendResult sent, TimeSpan took)
        {
            round.Sent++;
            _sizer?.OnSuccess(took, Math.Min(_packetCap, Math.Max(_options.BacklogPacketEvents, _options.MaxPacketEvents)));
            var policyResult = ApplyPolicy(new ServerPolicy(V1Client.PolicyMode(sent.PolicyMode), sent.DiscardPending, sent.NextCheckSeconds));
            if (policyResult != null) return policyResult;
            round.BatchSize = NextPacketSize(queue);
            // draining a backlog: a short pause between packets so the upload does not fight the game for the connection (a forced flush has no pause)
            if (!force && _options.BacklogPacketPause > TimeSpan.Zero && queue.PendingCount >= FullPacket())
            {
                var tpz = AnalyticsProf.Begin();
                Thread.Sleep(_options.BacklogPacketPause);
                AnalyticsProf.End(Stage.UploadPause, tpz);
            }
            return Next;
        }

        /// <summary>One V1 batch. Returns <see cref="Next"/> to go on or a result to stop.</summary>
        private UploadResult SendV1(IAnalyticsQueueBridge queue, DateTimeOffset now, UploadRound round)
        {
            if (_v8 != null && !_registered)
            {
                // V8 let this batch go to V1: the installation it was issued (adopted into the queue) is registered there the first time
                var registration = _v1.RegisterWithCredentialRecovery(queue, queue.GetState());
                if (!registration.Response.IsSuccess) return HandleFailure(registration.Response, now);
                _registered = true;
            }
            var state = queue.GetState();
            var events = queue.ReadOldest(Math.Min(round.BatchSize, PacketSizer.V1BatchLimit));
            if (events.Count == 0)
            {
                ResetBackoff();
                return UploadResult.Uploaded;
            }
            var batch = BuildV1Batch(queue, state, events);
            batch.Response = _v1.SendBatch(state, batch.Raw);
            if (batch.Response.StatusCode == 401)
            {
                var stop = ReregisterAndResend(queue, state, events, ref batch, now);
                if (stop != null) return stop;
            }
            var response = batch.Response;
            if (response.StatusCode == 413)
                return OnBatchTooLarge(queue, round, events, batch);
            if (!response.IsSuccess)
                return HandleFailure(response, now);

            var acknowledgement = V1Client.ParseAcknowledgement(response.Body, batch.SentIds);
            queue.DeleteAcknowledged(V1Client.SerializeStrings(batch.DerivedToOriginal == null ? acknowledgement.EventIds : ToOriginalIds(acknowledgement.EventIds, batch.DerivedToOriginal)));
            round.Sent++;
            return ApplyPolicy(acknowledgement.Policy) ?? Next;
        }

        private UploadResult OnBatchTooLarge(IAnalyticsQueueBridge queue, UploadRound round, QueueBatch events, V1Batch batch)
        {
            if (events.Count == 1)
                queue.DeleteAcknowledged(V1Client.SerializeStrings(batch.OriginalIds));
            else
                round.BatchSize = Math.Max(1, events.Count / 2);
            return Next;
        }

        /// <summary>A 401 on a batch: register again and resend once. Returns a result when the upload must stop.</summary>
        private UploadResult ReregisterAndResend(IAnalyticsQueueBridge queue, AnalyticsQueueState state, QueueBatch events, ref V1Batch batch, DateTimeOffset now)
        {
            _registered = false;
            var registration = _v1.RegisterWithCredentialRecovery(queue, state);
            state = registration.State;
            if (!registration.Response.IsSuccess) return HandleFailure(registration.Response, now);
            _registered = true;
            var policyResult = ApplyPolicy(V1Client.ParseRegistrationPolicy(registration.Response.Body));
            if (policyResult != null) return policyResult;
            // Re-registration may have replaced the installation (and with it the stream): derive the ids again for what is now open.
            batch = BuildV1Batch(queue, state, events);
            batch.Response = _v1.SendBatch(state, batch.Raw);
            if (batch.Response.StatusCode == 401) _registered = false;
            return null;
        }

        private V1Batch BuildV1Batch(IAnalyticsQueueBridge queue, AnalyticsQueueState state, QueueBatch events)
        {
            var batch = new V1Batch { OriginalIds = EventIds(events) };
            batch.SentIds = batch.OriginalIds;
            var tb1 = AnalyticsProf.Begin();
            batch.Raw = events.ToJsonArray(_reader);
            AnalyticsProf.End(Stage.V1Build, tb1);
            if (TryUseDerivedIds(queue, state, events, out var derivedRaw, out var map))
            {
                // A V8 stream is open: V1 carries the ids the server derives for the same rows, so a row V8 already stored is a duplicate, not a copy.
                batch.Raw = derivedRaw;
                batch.DerivedToOriginal = map;
                batch.SentIds = new List<string>(map.Keys);
            }
            return batch;
        }

        /// <summary>Returned by a send step to say "go on with the next packet or batch".</summary>
        private static readonly UploadResult Next = new UploadResult(FlushStatus.Uploaded, null);

        private sealed class UploadRound { internal int BatchSize; internal int Sent; }

        private sealed class V1Batch
        {
            internal string Raw;
            internal IReadOnlyList<string> OriginalIds, SentIds;
            internal Dictionary<string, string> DerivedToOriginal;
            internal V1Client.V1Response Response;
        }

        /// <summary>Kept for the EditMode tests: the V1 acknowledgement parser lives in <see cref="V1Client"/>.</summary>
        internal static V1Client.Acknowledgement ParseAcknowledgement(string body, IReadOnlyList<string> sentIds) => V1Client.ParseAcknowledgement(body, sentIds);

        public void Dispose()
        {
            _v8?.Dispose();
            _client.Dispose();
        }

        private UploadResult HandleFailure(V1Client.V1Response response, DateTimeOffset now)
        {
            if (response.StatusCode == 409 && response.ErrorCode == "install_conflict")
            {
                _installConflict = true;
                return UploadResult.Deferred;
            }

            if (response.StatusCode == 401)
                return BackOff(now, response.RetryAfter);

            if (response.StatusCode != 408 && response.StatusCode != 429 && response.StatusCode < 500)
            {
                _permanentFailure = true;
                return UploadResult.Deferred;
            }

            return BackOff(now, response.RetryAfter);
        }

        private UploadResult BackOff(DateTimeOffset now, TimeSpan? retryAfter)
        {
            _nextAttemptAt = now + _retry.OnFailure(retryAfter);
            return UploadResult.Deferred;
        }

        private void ResetBackoff()
        {
            _retry.Reset();
            _nextAttemptAt = DateTimeOffset.MinValue;
            _nextUploadAt = DateTimeOffset.UtcNow.Add(_options.UploadInterval);
        }

        private UploadResult ApplyPolicy(ServerPolicy policy)
        {
            _currentPolicy = policy;
            _nextPolicyCheckAt = DateTimeOffset.UtcNow.AddSeconds(policy.NextCheckSeconds);
            _policyChanged?.Invoke(policy);
            if (policy.Mode == ServerPolicyMode.PauseUpload)
                return UploadResult.Deferred;
            return policy.Mode == ServerPolicyMode.DisableCollection ? UploadResult.Uploaded : null;
        }

        private static IReadOnlyList<string> EventIds(QueueBatch batch)
        {
            var ids = new List<string>(batch.Count);
            for (var index = 0; index < batch.Count; index++)
                ids.Add(batch.EventId(index));
            return ids;
        }

        /// <summary>
        /// When transport V8 is enabled and the queue has an open stream, rewrites the batch's event ids to their derived form.
        /// <paramref name="derivedToOriginal"/> maps each derived id back to the queue row's own id. Never throws: on any doubt V1 sends as it is.
        /// </summary>
        private bool TryUseDerivedIds(IAnalyticsQueueBridge queue, AnalyticsQueueState state, QueueBatch batch, out string derivedJson, out Dictionary<string, string> derivedToOriginal)
        {
            derivedJson = null;
            derivedToOriginal = null;
            if (_v8 == null)
                return false;
            try
            {
                var epoch = JsonUtility.FromJson<SequenceState>(queue.GetSequenceState()).stream_epoch;
                if (epoch <= 0)
                    return false;
                var derivedIds = new List<string>(batch.Count);
                derivedToOriginal = new Dictionary<string, string>(batch.Count, StringComparer.Ordinal);
                for (var index = 0; index < batch.Count; index++)
                {
                    var derived = V7Identity.DerivedEventId(_options.ProjectId, state.InstallationId, epoch, batch.Sequence(index));
                    derivedIds.Add(derived);
                    derivedToOriginal.Add(derived, batch.EventId(index));
                }
                derivedJson = batch.ToJsonArray(_reader, derivedIds);
                return true;
            }
            catch (Exception)
            {
                derivedJson = null;
                derivedToOriginal = null;
                return false;
            }
        }

        private static IReadOnlyList<string> ToOriginalIds(IReadOnlyList<string> derivedIds, Dictionary<string, string> derivedToOriginal)
        {
            var originals = new List<string>(derivedIds.Count);
            foreach (var id in derivedIds)
                originals.Add(derivedToOriginal[id]);
            return originals;
        }

        [Serializable] private sealed class SequenceState { public long stream_epoch; }
    }

    internal sealed class UploadResult
    {
        internal static readonly UploadResult Uploaded = new UploadResult(FlushStatus.Uploaded, null);
        internal static readonly UploadResult Deferred = new UploadResult(FlushStatus.UploadDeferred, null);
        internal static readonly UploadResult Persisted = new UploadResult(FlushStatus.PersistedToDevice, null);
        internal UploadResult(FlushStatus status, ServerPolicy policy) { Status = status; Policy = policy; }
        internal FlushStatus Status { get; }
        internal ServerPolicy Policy { get; }
    }
}
