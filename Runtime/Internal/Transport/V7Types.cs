using System;
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
        V7Response Get(string pathAndQuery, string credential);
    }

    /// <summary>Content-addressed cache for catalogs and dictionaries (a file name is the asset id).</summary>
    internal interface IV7AssetStore
    {
        byte[] TryRead(string kind, string id);
        void Write(string kind, string id, byte[] data);
        void Delete(string kind, string id);
    }

    internal sealed class MemoryV7AssetStore : IV7AssetStore
    {
        private readonly Dictionary<string, byte[]> _items = new Dictionary<string, byte[]>(StringComparer.Ordinal);
        public byte[] TryRead(string kind, string id) => _items.TryGetValue(kind + "/" + id, out var data) ? data : null;
        public void Write(string kind, string id, byte[] data) => _items[kind + "/" + id] = data;
        public void Delete(string kind, string id) => _items.Remove(kind + "/" + id);
    }

    internal sealed class FileV7AssetStore : IV7AssetStore
    {
        private readonly string _directory;
        internal FileV7AssetStore(string directory) { _directory = directory; }

        public byte[] TryRead(string kind, string id)
        {
            try { var path = PathFor(kind, id); return File.Exists(path) ? File.ReadAllBytes(path) : null; }
            catch (IOException) { return null; }
            catch (UnauthorizedAccessException) { return null; }
        }

        public void Write(string kind, string id, byte[] data)
        {
            try
            {
                Directory.CreateDirectory(_directory);
                var temporary = PathFor(kind, id) + ".tmp";
                File.WriteAllBytes(temporary, data);
                if (File.Exists(PathFor(kind, id))) File.Delete(PathFor(kind, id));
                File.Move(temporary, PathFor(kind, id));
            }
            catch (IOException) { /* a cache miss is only a refetch */ }
            catch (UnauthorizedAccessException) { }
        }

        public void Delete(string kind, string id)
        {
            try { File.Delete(PathFor(kind, id)); } catch (IOException) { } catch (UnauthorizedAccessException) { }
        }

        private string PathFor(string kind, string id) => Path.Combine(_directory, kind + "-" + id + ".bin");
    }

    /// <summary>HttpClient-backed <see cref="IV7Http"/>.</summary>
    internal sealed class HttpV7Transport : IV7Http
    {
        private readonly HttpClient _client;
        private readonly string _baseUrl;

        internal HttpV7Transport(HttpClient client, string serverUrl) { _client = client; _baseUrl = serverUrl.TrimEnd('/'); }

        public V7Response PostJson(string path, string json, string credential) => Send(HttpMethod.Post, path, JsonContent(json), null, credential);
        public V7Response PutJson(string path, string json, string credential) => Send(HttpMethod.Put, path, JsonContent(json), null, credential);

        public V7Response PostPacket(string path, byte[] packet, IReadOnlyDictionary<string, string> headers, string credential)
        {
            var content = new ByteArrayContent(packet);
            content.Headers.ContentType = new MediaTypeHeaderValue("application/vnd.mortris.m7");
            return Send(HttpMethod.Post, path, content, headers, credential);
        }

        public V7Response Get(string pathAndQuery, string credential) => Send(HttpMethod.Get, pathAndQuery, null, null, credential);

        private static HttpContent JsonContent(string json) => new StringContent(json, new UTF8Encoding(false), "application/json");

        private V7Response Send(HttpMethod method, string path, HttpContent content, IReadOnlyDictionary<string, string> headers, string credential)
        {
            using (var request = new HttpRequestMessage(method, new Uri(_baseUrl + path, UriKind.Absolute)) { Content = content })
            {
                if (!string.IsNullOrEmpty(credential)) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", credential);
                if (headers != null) foreach (var header in headers) request.Headers.TryAddWithoutValidation(header.Key, header.Value);
                using (var response = _client.SendAsync(request).GetAwaiter().GetResult())
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
