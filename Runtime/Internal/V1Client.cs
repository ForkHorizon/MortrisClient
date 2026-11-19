// V1 JSON client (register, policy, gzip batches): the fallback path of the V8 uploader.
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading;
using Daliys.Analytics.Internal.Transport;
using UnityEngine;

namespace Daliys.Analytics.Internal
{
    /// <summary>The V1 JSON API (registration, policy, gzip batches): the fallback of the binary transport. Single-threaded (the worker thread).</summary>
    internal sealed class V1Client
    {
        private readonly AnalyticsOptions _options;
        private readonly AnalyticsDeviceContext _device;
        private readonly HttpClient _client;
        private readonly Func<CancellationToken> _deadline;

        internal V1Client(AnalyticsOptions options, AnalyticsDeviceContext device, HttpClient client, Func<CancellationToken> deadline)
        {
            _options = options; _device = device; _client = client; _deadline = deadline;
        }

        private V1Response Register(AnalyticsQueueState state) => PostJson("/v1/installs/register", RegisterBody(_options, _device, state), null, false);

        /// <summary>The body of <c>POST /v1/installs/register</c> (shared with the browser pipeline).</summary>
        internal static string RegisterBody(AnalyticsOptions options, AnalyticsDeviceContext device, AnalyticsQueueState state) => JsonUtility.ToJson(new RegisterRequest
        {
            schema_version = 1, project_id = options.ProjectId, install_id = state.InstallationId,
            installation_credential = state.InstallationCredential, sdk_name = AnalyticsDeviceContext.SdkName,
            sdk_version = AnalyticsDeviceContext.SdkVersion, app_version = device.AppVersion,
            build_number = device.BuildNumber, platform = device.Platform,
        });

        internal RegistrationAttempt RegisterWithCredentialRecovery(IAnalyticsQueueBridge queue, AnalyticsQueueState state)
        {
            var response = Register(state);
            if (response.StatusCode == 400 && response.ErrorCode == "invalid_credential")
            {
                state = queue.ResetIdentity();
                response = Register(state);
            }
            return new RegistrationAttempt(state, response);
        }

        internal V1Response FetchPolicy(AnalyticsQueueState state) => PostJson("/v1/client/policy", PolicyBody(_options, _device, state), state.InstallationCredential, false);

        /// <summary>The body of <c>POST /v1/client/policy</c> (shared with the browser pipeline).</summary>
        internal static string PolicyBody(AnalyticsOptions options, AnalyticsDeviceContext device, AnalyticsQueueState state) => JsonUtility.ToJson(new PolicyRequest
        {
            schema_version = 1, project_id = options.ProjectId, install_id = state.InstallationId,
            sdk = new SdkInfo { name = AnalyticsDeviceContext.SdkName, version = AnalyticsDeviceContext.SdkVersion },
            app_version = device.AppVersion, build_number = device.BuildNumber, platform = device.Platform,
        });

        internal V1Response SendBatch(AnalyticsQueueState state, string eventsJson) =>
            PostJson("/v1/events/batch", BatchBody(_options, state, eventsJson), state.InstallationCredential, true);

        /// <summary>The body of <c>POST /v1/events/batch</c>; <paramref name="eventsJson"/> is the JSON array of events (shared with the browser pipeline).</summary>
        internal static string BatchBody(AnalyticsOptions options, AnalyticsQueueState state, string eventsJson)
        {
            var payload = new StringBuilder(eventsJson.Length + 256);
            payload.Append("{\"schema_version\":1,\"project_id\":"); EventRecordJson.AppendString(payload, options.ProjectId);
            payload.Append(",\"install_id\":"); EventRecordJson.AppendString(payload, state.InstallationId);
            payload.Append(",\"sdk\":{\"name\":"); EventRecordJson.AppendString(payload, AnalyticsDeviceContext.SdkName);
            payload.Append(",\"version\":"); EventRecordJson.AppendString(payload, AnalyticsDeviceContext.SdkVersion);
            payload.Append("},\"sent_at_client\":"); EventRecordJson.AppendString(payload, DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", System.Globalization.CultureInfo.InvariantCulture));
            payload.Append(",\"events\":").Append(eventsJson).Append('}');
            return payload.ToString();
        }

        private V1Response PostJson(string path, string body, string credential, bool gzip)
        {
            using (var request = new HttpRequestMessage(HttpMethod.Post, Endpoint(path)))
            {
                var tz = AnalyticsProf.Begin();
                request.Content = gzip ? GzipContent(body) : new StringContent(body, Encoding.UTF8, "application/json");
                if (gzip) AnalyticsProf.End(Stage.V1Gzip, tz);
                if (!string.IsNullOrEmpty(credential))
                    request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", credential);

                var th = AnalyticsProf.Begin();
                var sent = _client.SendAsync(request, _deadline()).GetAwaiter().GetResult();
                AnalyticsProf.End(Stage.V1Http, th);
                using (var response = sent)
                {
                    var responseBody = response.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                    return new V1Response((int)response.StatusCode, responseBody, RetryAfter(response));
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

        internal static ServerPolicyMode PolicyMode(string mode) =>
            mode == "active" ? ServerPolicyMode.Active : mode == "pause_upload" ? ServerPolicyMode.PauseUpload : mode == "disable_collection" ? ServerPolicyMode.DisableCollection : throw new InvalidDataException("Unknown client policy mode.");

        internal static ServerPolicy ParseRegistrationPolicy(string body)
        {
            var payload = JsonUtility.FromJson<RegisterResponse>(body);
            if (payload == null || string.IsNullOrWhiteSpace(payload.server_time) || payload.installation_status != "registered")
                throw new InvalidDataException("Registration response is invalid.");
            return RequirePolicy(payload.client_policy);
        }

        internal static ServerPolicy ParsePolicy(string body)
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

        /// <summary>A Retry-After header value (seconds or an HTTP date) as a delay; null when absent or unreadable.</summary>
        internal static TimeSpan? ParseRetryAfter(string value, DateTimeOffset now)
        {
            if (string.IsNullOrWhiteSpace(value)) return null;
            if (int.TryParse(value.Trim(), System.Globalization.NumberStyles.None, System.Globalization.CultureInfo.InvariantCulture, out var seconds)) return TimeSpan.FromSeconds(seconds);
            if (DateTimeOffset.TryParse(value, System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.AssumeUniversal, out var date)) return date - now;
            return null;
        }

        private static TimeSpan? RetryAfter(HttpResponseMessage response)
        {
            var retryAfter = response.Headers.RetryAfter;
            if (retryAfter?.Delta != null) return retryAfter.Delta;
            if (retryAfter?.Date != null) return retryAfter.Date.Value - DateTimeOffset.UtcNow;
            return null;
        }

        internal static string SerializeStrings(IReadOnlyList<string> values)
        {
            var payload = new StringBuilder("[");
            for (var index = 0; index < values.Count; index++)
            {
                if (index > 0) payload.Append(',');
                EventRecordJson.AppendString(payload, values[index]);
            }
            return payload.Append(']').ToString();
        }

        internal sealed class Acknowledgement
        {
            internal Acknowledgement(IReadOnlyList<string> eventIds, ServerPolicy policy) { EventIds = eventIds; Policy = policy; }
            internal IReadOnlyList<string> EventIds { get; }
            internal ServerPolicy Policy { get; }
        }

        internal sealed class V1Response
        {
            internal V1Response(int statusCode, string body, TimeSpan? retryAfter)
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

        internal sealed class RegistrationAttempt
        {
            internal RegistrationAttempt(AnalyticsQueueState state, V1Response response)
            {
                State = state;
                Response = response;
            }

            internal AnalyticsQueueState State { get; }
            internal V1Response Response { get; }
        }

        [Serializable] private sealed class RegisterRequest { public int schema_version; public string project_id; public string install_id; public string installation_credential; public string sdk_name; public string sdk_version; public string app_version; public string build_number; public string platform; }
        [Serializable] private sealed class PolicyRequest { public int schema_version; public string project_id; public string install_id; public SdkInfo sdk; public string app_version; public string build_number; public string platform; }
        [Serializable] private sealed class SdkInfo { public string name; public string version; }
        [Serializable] private sealed class RegisterResponse : PolicyResponse { public string installation_status; }
        [Serializable] private sealed class BatchResponse : PolicyResponse { public string[] accepted; public string[] duplicates; public RejectedEvent[] rejected; }
        [Serializable] private class PolicyResponse { public string server_time; public PolicyResponsePolicy client_policy; }
        [Serializable] private sealed class PolicyResponsePolicy { public string mode; public int next_check_seconds; public bool discard_pending; }
        [Serializable] private sealed class RejectedEvent { public string event_id; public string code; }
        [Serializable] private sealed class ErrorResponse { public string code; }
    }
}
