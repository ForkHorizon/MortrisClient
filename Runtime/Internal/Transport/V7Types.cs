// Request and response types of the V7 transport.
using System;
using System.Threading;
using System.IO;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>A server response to a V7 request.</summary>
    internal sealed class V7Response
    {
        internal V7Response(int status, byte[] body, TimeSpan? retryAfter)
        {
            Status = status;
            Body = body ?? new byte[0];
            RetryAfter = retryAfter;
            Text = Encoding.UTF8.GetString(Body);
            try { ErrorCode = (MiniJson.Parse(Text) as Dictionary<string, object>)?["code"] as string; } catch (Exception) { }
        }

        internal int Status { get; }
        internal byte[] Body { get; }
        internal string Text { get; }
        internal string ErrorCode { get; }
        internal TimeSpan? RetryAfter { get; }
        internal bool IsSuccess => Status >= 200 && Status < 300;
    }

    /// <summary>The HTTP calls the V7 session needs. Synchronous: it runs on the SDK's worker thread.</summary>
    internal interface IV7Http
    {
        V7Response PostJson(string path, string json, string credential);
        V7Response PutJson(string path, string json, string credential);
        V7Response PostPacket(string path, byte[] packet, IReadOnlyDictionary<string, string> headers, string credential);
        /// <summary>A binary body with the given media type (V8 packets).</summary>
        V7Response PostBinary(string path, byte[] body, string contentType, string credential);
        V7Response Get(string pathAndQuery, string credential);
    }

    /// <summary>A cancellation token that can be swapped atomically.</summary>
    internal sealed class CancellationTokenSourceBox
    {
        internal static readonly CancellationTokenSourceBox None = new CancellationTokenSourceBox(CancellationToken.None);
        internal readonly CancellationToken Token;
        internal CancellationTokenSourceBox(CancellationToken token) { Token = token; }
    }

    /// <summary>HttpClient-backed <see cref="IV7Http"/>.</summary>
    internal sealed class HttpV7Transport : IV7Http
    {
        private readonly HttpClient _client;
        private readonly string _baseUrl;

        /// <summary>Cancels requests still running when it is signalled (a background upload has a short allowance).</summary>
        internal volatile CancellationTokenSourceBox Deadline = CancellationTokenSourceBox.None;

        /// <summary>The client every analytics request goes through. A redirect is never followed: a POST body (and the
        /// credential) must go to the configured server only, so a 3xx surfaces as a plain non-success status.</summary>
        internal static HttpClient CreateClient()
        {
            var handler = new HttpClientHandler { AllowAutoRedirect = false, AutomaticDecompression = System.Net.DecompressionMethods.GZip };
#if DALIYS_ANALYTICS_PROFILE
            // the profiling build talks to a local TLS meter (comparison-run~/tools/tlsmeter.py) that has a self-made certificate; never in the shipped SDK
            handler.ServerCertificateCustomValidationCallback = (message, certificate, chain, errors) => true;
#endif
            return new HttpClient(handler);
        }

        internal HttpV7Transport(HttpClient client, string serverUrl) { _client = client; _baseUrl = serverUrl.TrimEnd('/'); }

        public V7Response PostJson(string path, string json, string credential) => Send(HttpMethod.Post, path, JsonContent(json), null, credential);
        public V7Response PutJson(string path, string json, string credential) => Send(HttpMethod.Put, path, JsonContent(json), null, credential);

        public V7Response PostPacket(string path, byte[] packet, IReadOnlyDictionary<string, string> headers, string credential)
        {
            var content = new ByteArrayContent(packet);
            content.Headers.ContentType = new MediaTypeHeaderValue("application/vnd.mortris.m7");
            return Send(HttpMethod.Post, path, content, headers, credential);
        }

        public V7Response PostBinary(string path, byte[] body, string contentType, string credential)
        {
            var content = new ByteArrayContent(body);
            content.Headers.ContentType = new MediaTypeHeaderValue(contentType);
            return Send(HttpMethod.Post, path, content, null, credential);
        }

        public V7Response Get(string pathAndQuery, string credential) => Send(HttpMethod.Get, pathAndQuery, null, null, credential);

        private static HttpContent JsonContent(string json) => new StringContent(json, new UTF8Encoding(false), "application/json");

        private V7Response Send(HttpMethod method, string path, HttpContent content, IReadOnlyDictionary<string, string> headers, string credential)
        {
            AnalyticsProf.Count(AnalyticsProf.Counter.Requests);
            using (var request = new HttpRequestMessage(method, new Uri(_baseUrl + path, UriKind.Absolute)) { Content = content })
            {
                if (!string.IsNullOrEmpty(credential)) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", credential);
                if (headers != null) foreach (var header in headers) request.Headers.TryAddWithoutValidation(header.Key, header.Value);
                using (var response = _client.SendAsync(request, Deadline.Token).GetAwaiter().GetResult())
                {
                    var body = response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult();
                    TimeSpan? retryAfter = response.Headers.RetryAfter?.Delta;
                    if (retryAfter == null && response.Headers.RetryAfter?.Date != null) retryAfter = response.Headers.RetryAfter.Date.Value - DateTimeOffset.UtcNow;
                    return new V7Response((int)response.StatusCode, body, retryAfter);
                }
            }
        }
    }
}
