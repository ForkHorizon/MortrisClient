using System;
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
        private const int MaximumBatchSize = 100;
        private static readonly TimeSpan InitialBackoff = TimeSpan.FromSeconds(5);
        private static readonly TimeSpan MaximumBackoff = TimeSpan.FromMinutes(5);

        private readonly AnalyticsOptions _options;
        private readonly AnalyticsDeviceContext _device;
        private readonly Action<ServerPolicy> _policyChanged;
        private readonly HttpClient _client = new HttpClient();
        private DateTimeOffset _nextAttemptAt;
        private DateTimeOffset _nextPolicyCheckAt;
        private DateTimeOffset _nextUploadAt;
        private TimeSpan _backoff = InitialBackoff;
        private bool _registered;
        private bool _installConflict;
        private bool _permanentFailure;
        private ServerPolicy _currentPolicy;
        private readonly V7Session _v7;

        internal AnalyticsUploader(AnalyticsOptions options, AnalyticsDeviceContext device, Action<ServerPolicy> policyChanged)
        {
            _options = options;
            _device = device;
            _policyChanged = policyChanged;
            _nextUploadAt = DateTimeOffset.UtcNow.Add(options.UploadInterval);
            _v7 = CreateV7Session();
        }

        /// <summary>Test seam: a session with injected HTTP, storage and compressor.</summary>
        internal AnalyticsUploader(AnalyticsOptions options, AnalyticsDeviceContext device, Action<ServerPolicy> policyChanged, V7Session v7) 
        {
            _options = options;
            _device = device;
            _policyChanged = policyChanged;
            _nextUploadAt = DateTimeOffset.UtcNow.Add(options.UploadInterval);
            _v7 = v7;
        }

        private V7Session CreateV7Session()
        {
            if (!_options.UseTransportV7) return null;
            try
            {
                // Created on the Unity main thread (the worker is constructed by Analytics.Initialize), where persistentDataPath is legal.
                var directory = Path.Combine(Application.persistentDataPath, "daliys-analytics", "v7");
                var settings = new V7Settings { ProjectId = _options.ProjectId, SdkName = AnalyticsDeviceContext.SdkName, SdkVersion = AnalyticsDeviceContext.SdkVersion };
                return new V7Session(settings, new HttpV7Transport(_client, _options.ServerUrl), new FileV7AssetStore(directory));
            }
            catch (Exception exception)
            {
                if (_options.DebugLogging) Debug.LogException(exception);
                return null;
            }
        }

        internal UploadResult Flush(IAnalyticsQueueBridge queue, bool force)
        {
            var now = DateTimeOffset.UtcNow;
            if (_installConflict || _permanentFailure || (!force && now < _nextAttemptAt))
                return UploadResult.Deferred;

            try
            {
                var state = queue.GetState();
                if (!force && now < _nextUploadAt && state.PendingCount < _options.UploadEventThreshold)
                    return UploadResult.Persisted;

                if (!_registered)
                {
                    var registration = RegisterWithCredentialRecovery(queue, state);
                    state = registration.State;
                    if (!registration.Response.IsSuccess)
                        return HandleFailure(registration.Response, now);
                    _registered = true;
                    var policyResult = ApplyPolicy(ParseRegistrationPolicy(registration.Response.Body));
                    if (policyResult != null)
                        return policyResult;
                }
                else if (now >= _nextPolicyCheckAt)
                {
                    var policy = FetchPolicy(state);
                    if (policy.StatusCode == 401)
                    {
                        _registered = false;
                        var registration = RegisterWithCredentialRecovery(queue, state);
                        state = registration.State;
                        if (!registration.Response.IsSuccess)
                            return HandleFailure(registration.Response, now);
                        _registered = true;
                        var policyResult = ApplyPolicy(ParseRegistrationPolicy(registration.Response.Body));
                        if (policyResult != null)
                            return policyResult;
                    }
                    else
                    {
                        if (!policy.IsSuccess)
                            return HandleFailure(policy, now);
                        var policyResult = ApplyPolicy(ParsePolicy(policy.Body));
                        if (policyResult != null)
                            return policyResult;
                    }
                }

                if (_currentPolicy != null && _currentPolicy.Mode == ServerPolicyMode.PauseUpload)
                    return UploadResult.Deferred;
                if (_currentPolicy != null && _currentPolicy.Mode == ServerPolicyMode.DisableCollection)
                    return UploadResult.Uploaded;

                var batchSize = MaximumBatchSize;
                while (true)
                {
                    if (_v7 != null && !_v7.Disabled)
                    {
                        var v7 = _v7.Send(queue, state, () => queue.ReadOldestBatch(batchSize));
                        switch (v7.Kind)
                        {
                            case V7ResultKind.Delivered:
                            {
                                var policyResultAfterPacket = ApplyPolicy(new ServerPolicy(PolicyMode(v7.PolicyMode), v7.DiscardPending, v7.NextCheckSeconds));
                                if (policyResultAfterPacket != null)
                                    return policyResultAfterPacket;
                                continue;
                            }
                            case V7ResultKind.Empty:
                                ResetBackoff();
                                return UploadResult.Uploaded;
                            case V7ResultKind.Retry:
                                return BackOff(now, v7.RetryAfter);
                            case V7ResultKind.Unauthorized:
                            {
                                _registered = false;
                                var registration = RegisterWithCredentialRecovery(queue, state);
                                state = registration.State;
                                if (!registration.Response.IsSuccess)
                                    return HandleFailure(registration.Response, now);
                                _registered = true;
                                var policyResult = ApplyPolicy(ParseRegistrationPolicy(registration.Response.Body));
                                if (policyResult != null)
                                    return policyResult;
                                continue;
                            }
                            case V7ResultKind.PayloadTooLarge:
                                if (batchSize > 1)
                                {
                                    batchSize = Math.Max(1, batchSize / 2);
                                    continue;
                                }
                                break; // one event that cannot fit a packet: V1 decides what to do with it
                            default:
                                break; // Fallback: this batch goes through V1
                        }
                    }

                    var events = ParseQueuedEvents(queue.ReadOldestBatch(batchSize));
                    if (events.events == null || events.events.Length == 0)
                    {
                        ResetBackoff();
                        return UploadResult.Uploaded;
                    }

                    var originalIds = EventIds(events.events);
                    var sentIds = originalIds;
                    var raw = events.raw;
                    Dictionary<string, string> derivedToOriginal = null;
                    if (TryUseDerivedIds(queue, state, events.raw, out var derivedRaw, out var map))
                    {
                        // A V7 stream is open: V1 carries the ids the server derives for the same rows, so a row V7 already stored is a duplicate, not a copy.
                        raw = derivedRaw;
                        derivedToOriginal = map;
                        sentIds = new List<string>(map.Keys);
                    }
                    var response = SendBatch(state, raw);
                    if (response.StatusCode == 401)
                    {
                        _registered = false;
                        var registration = RegisterWithCredentialRecovery(queue, state);
                        state = registration.State;
                        if (!registration.Response.IsSuccess)
                            return HandleFailure(registration.Response, now);
                        _registered = true;
                        var policyResult = ApplyPolicy(ParseRegistrationPolicy(registration.Response.Body));
                        if (policyResult != null)
                            return policyResult;
                        // Re-registration may have replaced the installation (and with it the stream): derive the ids again for what is now open.
                        raw = events.raw;
                        derivedToOriginal = null;
                        sentIds = originalIds;
                        if (TryUseDerivedIds(queue, state, events.raw, out derivedRaw, out map))
                        {
                            raw = derivedRaw;
                            derivedToOriginal = map;
                            sentIds = new List<string>(map.Keys);
                        }
                        response = SendBatch(state, raw);
                        if (response.StatusCode == 401)
                            _registered = false;
                    }

                    if (response.StatusCode == 413)
                    {
                        if (events.events.Length == 1)
                        {
                            queue.DeleteAcknowledged(SerializeStrings(originalIds));
                            continue;
                        }
                        batchSize = Math.Max(1, events.events.Length / 2);
                        continue;
                    }

                    if (!response.IsSuccess)
                        return HandleFailure(response, now);

                    var acknowledgement = ParseAcknowledgement(response.Body, sentIds);
                    queue.DeleteAcknowledged(SerializeStrings(derivedToOriginal == null ? acknowledgement.EventIds : ToOriginalIds(acknowledgement.EventIds, derivedToOriginal)));
                    var policyResultAfterBatch = ApplyPolicy(acknowledgement.Policy);
                    if (policyResultAfterBatch != null)
                        return policyResultAfterBatch;
                }
            }
            catch (Exception)
            {
                return BackOff(now, null);
            }
        }

        public void Dispose()
        {
            _v7?.Dispose();
            _client.Dispose();
        }

        private ServerResponse Register(AnalyticsQueueState state) => PostJson("/v1/installs/register", JsonUtility.ToJson(new RegisterRequest
        {
            schema_version = 1, project_id = _options.ProjectId, install_id = state.InstallationId,
            installation_credential = state.InstallationCredential, sdk_name = AnalyticsDeviceContext.SdkName,
            sdk_version = AnalyticsDeviceContext.SdkVersion, app_version = _device.AppVersion,
            build_number = _device.BuildNumber, platform = _device.Platform,
        }), null, false);

        private RegistrationAttempt RegisterWithCredentialRecovery(IAnalyticsQueueBridge queue, AnalyticsQueueState state)
        {
            var response = Register(state);
            if (response.StatusCode == 400 && response.ErrorCode == "invalid_credential")
            {
                state = queue.ResetIdentity();
                response = Register(state);
            }
            return new RegistrationAttempt(state, response);
        }

        private ServerResponse FetchPolicy(AnalyticsQueueState state) => PostJson("/v1/client/policy", JsonUtility.ToJson(new PolicyRequest
        {
            schema_version = 1, project_id = _options.ProjectId, install_id = state.InstallationId,
            sdk = new SdkInfo { name = AnalyticsDeviceContext.SdkName, version = AnalyticsDeviceContext.SdkVersion },
            app_version = _device.AppVersion, build_number = _device.BuildNumber, platform = _device.Platform,
        }), state.InstallationCredential, false);

        private ServerResponse SendBatch(AnalyticsQueueState state, string eventsJson)
        {
            var payload = new StringBuilder();
            payload.Append("{\"schema_version\":1,\"project_id\":"); AppendJsonString(payload, _options.ProjectId);
            payload.Append(",\"install_id\":"); AppendJsonString(payload, state.InstallationId);
            payload.Append(",\"sdk\":{\"name\":"); AppendJsonString(payload, AnalyticsDeviceContext.SdkName);
            payload.Append(",\"version\":"); AppendJsonString(payload, AnalyticsDeviceContext.SdkVersion);
            payload.Append("},\"sent_at_client\":"); AppendJsonString(payload, DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'"));
            payload.Append(",\"events\":").Append(eventsJson).Append('}');
            return PostJson("/v1/events/batch", payload.ToString(), state.InstallationCredential, true);
        }

        private ServerResponse PostJson(string path, string body, string credential, bool gzip)
        {
            using (var request = new HttpRequestMessage(HttpMethod.Post, Endpoint(path)))
            {
                request.Content = gzip ? GzipContent(body) : new StringContent(body, Encoding.UTF8, "application/json");
                if (!string.IsNullOrEmpty(credential))
                    request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", credential);

                using (var response = _client.SendAsync(request).GetAwaiter().GetResult())
                {
                    var responseBody = response.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                    return new ServerResponse((int)response.StatusCode, responseBody, RetryAfter(response));
                }
            }
        }

        private Uri Endpoint(string path) => new Uri(_options.ServerUrl.TrimEnd('/') + path, UriKind.Absolute);

        private static HttpContent GzipContent(string body)
        {
            using (var bytes = new MemoryStream())
            {
                using (var gzip = new GZipStream(bytes, System.IO.Compression.CompressionLevel.Fastest, true))
                using (var writer = new StreamWriter(gzip, new UTF8Encoding(false)))
                    writer.Write(body);

                var content = new ByteArrayContent(bytes.ToArray());
                content.Headers.ContentType = new MediaTypeHeaderValue("application/json");
                content.Headers.ContentEncoding.Add("gzip");
                return content;
            }
        }

        private UploadResult HandleFailure(ServerResponse response, DateTimeOffset now)
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
            _nextAttemptAt = now + (retryAfter ?? _backoff);
            _backoff = TimeSpan.FromMilliseconds(Math.Min(_backoff.TotalMilliseconds * 2, MaximumBackoff.TotalMilliseconds));
            return UploadResult.Deferred;
        }

        private void ResetBackoff()
        {
            _backoff = InitialBackoff;
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

        private static QueuedEvents ParseQueuedEvents(string raw)
        {
            var parsed = JsonUtility.FromJson<QueuedEvents>("{\"events\":" + raw + "}");
            if (parsed == null)
                throw new InvalidDataException("Queued event batch is invalid JSON.");
            parsed.raw = raw;
            return parsed;
        }

        private static IReadOnlyList<string> EventIds(QueuedEvent[] events)
        {
            var ids = new List<string>(events.Length);
            foreach (var queuedEvent in events)
            {
                if (string.IsNullOrEmpty(queuedEvent.event_id))
                    throw new InvalidDataException("Queued event has no event_id.");
                ids.Add(queuedEvent.event_id);
            }
            return ids;
        }

        internal static Acknowledgement ParseAcknowledgement(string body, IReadOnlyList<string> sentIds)
        {
            var payload = JsonUtility.FromJson<BatchResponse>(body);
            if (payload == null || string.IsNullOrWhiteSpace(payload.server_time))
                throw new InvalidDataException("Batch response has no server_time.");

            var ids = new List<string>(sentIds.Count);
            var seen = new HashSet<string>(StringComparer.Ordinal);
            AddAcknowledgements(payload.accepted, sentIds, seen, ids);
            AddAcknowledgements(payload.duplicates, sentIds, seen, ids);
            if (payload.rejected == null)
                throw new InvalidDataException("Batch response omitted an acknowledgement list.");
            foreach (var rejected in payload.rejected)
            {
                if (string.IsNullOrWhiteSpace(rejected.code))
                    throw new InvalidDataException("Batch response rejection has no code.");
                AddAcknowledgement(rejected.event_id, sentIds, seen, ids);
            }
            return new Acknowledgement(ids, RequirePolicy(payload.client_policy));
        }

        private static void AddAcknowledgements(IEnumerable<string> values, IReadOnlyList<string> sentIds, ISet<string> seen, ICollection<string> acknowledgements)
        {
            if (values == null)
                throw new InvalidDataException("Batch response omitted an acknowledgement list.");
            foreach (var value in values)
                AddAcknowledgement(value, sentIds, seen, acknowledgements);
        }

        private static void AddAcknowledgement(string id, IReadOnlyList<string> sentIds, ISet<string> seen, ICollection<string> acknowledgements)
        {
            if (string.IsNullOrEmpty(id) || !Contains(sentIds, id) || !seen.Add(id))
                throw new InvalidDataException("Batch response acknowledgement is invalid.");
            acknowledgements.Add(id);
        }

        private static bool Contains(IReadOnlyList<string> values, string candidate)
        {
            for (var index = 0; index < values.Count; index++)
                if (string.Equals(values[index], candidate, StringComparison.Ordinal)) return true;
            return false;
        }

        /// <summary>
        /// When transport V7 is enabled and the queue has an open stream, rewrites the batch's event ids to their derived form.
        /// <paramref name="derivedToOriginal"/> maps each derived id back to the queue row's own id. Never throws: on any doubt V1 sends as it is.
        /// </summary>
        private bool TryUseDerivedIds(IAnalyticsQueueBridge queue, AnalyticsQueueState state, string batchJson, out string derivedJson, out Dictionary<string, string> derivedToOriginal)
        {
            derivedJson = null;
            derivedToOriginal = null;
            if (!_options.UseTransportV7)
                return false;
            try
            {
                var epoch = JsonUtility.FromJson<SequenceState>(queue.GetSequenceState()).stream_epoch;
                if (epoch <= 0)
                    return false;
                derivedJson = V7Identity.RewriteEventIds(batchJson, _options.ProjectId, state.InstallationId, epoch, out var ids);
                derivedToOriginal = new Dictionary<string, string>(ids.Count, StringComparer.Ordinal);
                foreach (var pair in ids)
                    derivedToOriginal.Add(pair.Value, pair.Key);
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

        private static ServerPolicyMode PolicyMode(string mode) =>
            mode == "active" ? ServerPolicyMode.Active : mode == "pause_upload" ? ServerPolicyMode.PauseUpload : mode == "disable_collection" ? ServerPolicyMode.DisableCollection : throw new InvalidDataException("Unknown client policy mode.");

        private static ServerPolicy ParseRegistrationPolicy(string body)
        {
            var payload = JsonUtility.FromJson<RegisterResponse>(body);
            if (payload == null || string.IsNullOrWhiteSpace(payload.server_time) || payload.installation_status != "registered")
                throw new InvalidDataException("Registration response is invalid.");
            return RequirePolicy(payload.client_policy);
        }

        private static ServerPolicy ParsePolicy(string body)
        {
            var payload = JsonUtility.FromJson<PolicyResponse>(body);
            if (payload == null || string.IsNullOrWhiteSpace(payload.server_time))
                throw new InvalidDataException("Policy response is invalid.");
            return RequirePolicy(payload.client_policy);
        }

        private static ServerPolicy RequirePolicy(PolicyResponsePolicy policy)
        {
            if (policy == null)
                throw new InvalidDataException("Response has no valid client_policy.");
            if (policy.next_check_seconds < 1)
                throw new InvalidDataException("Response client_policy has an invalid next_check_seconds.");
            var mode = policy.mode == "active" ? ServerPolicyMode.Active : policy.mode == "pause_upload" ? ServerPolicyMode.PauseUpload : policy.mode == "disable_collection" ? ServerPolicyMode.DisableCollection : throw new InvalidDataException("Unknown client policy mode.");
            return new ServerPolicy(mode, policy.discard_pending, policy.next_check_seconds);
        }

        private static TimeSpan? RetryAfter(HttpResponseMessage response)
        {
            var retryAfter = response.Headers.RetryAfter;
            if (retryAfter?.Delta != null) return retryAfter.Delta;
            if (retryAfter?.Date != null) return retryAfter.Date.Value - DateTimeOffset.UtcNow;
            return null;
        }

        private static string SerializeStrings(IReadOnlyList<string> values)
        {
            var payload = new StringBuilder("[");
            for (var index = 0; index < values.Count; index++)
            {
                if (index > 0) payload.Append(',');
                AppendJsonString(payload, values[index]);
            }
            return payload.Append(']').ToString();
        }

        private static void AppendJsonString(StringBuilder payload, string value)
        {
            payload.Append('"');
            foreach (var character in value)
            {
                switch (character)
                {
                    case '"': payload.Append("\\\""); break;
                    case '\\': payload.Append("\\\\"); break;
                    case '\b': payload.Append("\\b"); break;
                    case '\f': payload.Append("\\f"); break;
                    case '\n': payload.Append("\\n"); break;
                    case '\r': payload.Append("\\r"); break;
                    case '\t': payload.Append("\\t"); break;
                    default:
                        if (character < ' ') payload.Append("\\u").Append(((int)character).ToString("x4"));
                        else payload.Append(character);
                        break;
                }
            }
            payload.Append('"');
        }

        internal sealed class Acknowledgement
        {
            internal Acknowledgement(IReadOnlyList<string> eventIds, ServerPolicy policy) { EventIds = eventIds; Policy = policy; }
            internal IReadOnlyList<string> EventIds { get; }
            internal ServerPolicy Policy { get; }
        }

        private sealed class ServerResponse
        {
            internal ServerResponse(int statusCode, string body, TimeSpan? retryAfter)
            {
                StatusCode = statusCode; Body = body; RetryAfter = retryAfter;
                try { ErrorCode = JsonUtility.FromJson<ErrorResponse>(body)?.code; } catch (Exception) { }
            }
            internal int StatusCode { get; }
            internal string Body { get; }
            internal TimeSpan? RetryAfter { get; }
            internal string ErrorCode { get; }
            internal bool IsSuccess => StatusCode >= 200 && StatusCode < 300;
        }

        private sealed class RegistrationAttempt
        {
            internal RegistrationAttempt(AnalyticsQueueState state, ServerResponse response)
            {
                State = state;
                Response = response;
            }

            internal AnalyticsQueueState State { get; }
            internal ServerResponse Response { get; }
        }

        [Serializable] private sealed class RegisterRequest { public int schema_version; public string project_id; public string install_id; public string installation_credential; public string sdk_name; public string sdk_version; public string app_version; public string build_number; public string platform; }
        [Serializable] private sealed class PolicyRequest { public int schema_version; public string project_id; public string install_id; public SdkInfo sdk; public string app_version; public string build_number; public string platform; }
        [Serializable] private sealed class SdkInfo { public string name; public string version; }
        [Serializable] private sealed class SequenceState { public long stream_epoch; }
        [Serializable] private sealed class QueuedEvents { public QueuedEvent[] events; [NonSerialized] public string raw; }
        [Serializable] private sealed class QueuedEvent { public string event_id; }
        [Serializable] private sealed class RegisterResponse : PolicyResponse { public string installation_status; }
        [Serializable] private sealed class BatchResponse : PolicyResponse { public string[] accepted; public string[] duplicates; public RejectedEvent[] rejected; }
        [Serializable] private class PolicyResponse { public string server_time; public PolicyResponsePolicy client_policy; }
        [Serializable] private sealed class PolicyResponsePolicy { public string mode; public int next_check_seconds; public bool discard_pending; }
        [Serializable] private sealed class RejectedEvent { public string event_id; public string code; }
        [Serializable] private sealed class ErrorResponse { public string code; }
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
