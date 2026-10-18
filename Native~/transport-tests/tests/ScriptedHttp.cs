using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using Daliys.Analytics.Internal.Transport;

namespace M7Transport.Tests
{
    /// <summary>A recorded request.</summary>
    internal sealed class Call
    {
        internal string Method, Path, Body;
        internal byte[] Packet;
        internal IReadOnlyDictionary<string, string> Headers;
        internal string Credential;
    }

    /// <summary>
    /// Stand-in for the server: the test decides every answer. Defaults implement a healthy server whose acknowledgement is whatever
    /// <see cref="Ack"/> returns (the packet itself is not decoded here; the Go server tests and the integration test cover decoding).
    /// </summary>
    internal sealed class ScriptedHttp : IV7Http
    {
        internal readonly List<Call> Calls = new List<Call>();
        internal Func<Call, V7Response> Override;           // returns null to use the default behaviour
        internal Func<long> Ack = () => 0;         // acknowledgement returned with a packet
        internal Func<long> SyncAck = () => 0;     // acknowledgement returned with a stream sync (what the server already holds)
        internal long Epoch = 1;
        internal string CatalogId = "", DictionaryId = "";
        internal byte[] Catalog, Dictionary;
        internal string AliasEpoch = "";
        internal int AliasCount;

        internal ScriptedHttp(byte[] catalog, byte[] dictionary)
        {
            Catalog = catalog; Dictionary = dictionary;
            CatalogId = Id(catalog); DictionaryId = dictionary == null ? "" : Id(dictionary);
        }

        internal static string Id(byte[] data)
        {
            using (var sha = SHA256.Create()) { var h = sha.ComputeHash(data); var b = new StringBuilder(); for (var i = 0; i < 8; i++) b.Append(h[i].ToString("x2")); return b.ToString(); }
        }

        internal static V7Response Json(int status, string body, TimeSpan? retryAfter = null) => new V7Response(status, Encoding.UTF8.GetBytes(body), retryAfter);
        internal static V7Response Error(int status, string code, string message = "m") => Json(status, "{\"server_time\":\"t\",\"code\":\"" + code + "\",\"message\":\"" + message + "\",\"request_id\":\"r\"}");

        internal IEnumerable<Call> Where(string method, string path) { foreach (var c in Calls) if (c.Method == method && c.Path.StartsWith(path, StringComparison.Ordinal)) yield return c; }
        internal int Count(string method, string path) { var n = 0; foreach (var _ in Where(method, path)) n++; return n; }

        private V7Response Record(string method, string path, string body, byte[] packet, IReadOnlyDictionary<string, string> headers, string credential)
        {
            var call = new Call { Method = method, Path = path, Body = body, Packet = packet, Headers = headers, Credential = credential };
            Calls.Add(call);
            return Override?.Invoke(call) ?? Default(call);
        }

        public V7Response PostJson(string path, string json, string credential) => Record("POST", path, json, null, null, credential);
        public V7Response PutJson(string path, string json, string credential) => Record("PUT", path, json, null, null, credential);
        public V7Response PostPacket(string path, byte[] packet, IReadOnlyDictionary<string, string> headers, string credential) => Record("POST", path, null, packet, headers, credential);
        public V7Response Get(string pathAndQuery, string credential) => Record("GET", pathAndQuery, null, null, null, credential);

        private V7Response Default(Call call)
        {
            if (call.Path == "/v2/streams/sync")
                return Json(200, "{\"server_time\":\"t\",\"epoch\":" + Epoch + ",\"ack_through\":" + SyncAck() + ",\"missing\":[],\"alias_epoch\":\"" + AliasEpoch + "\",\"alias_count\":" + AliasCount +
                                 ",\"assets\":{\"catalog_id\":\"" + CatalogId + "\",\"dictionary_id\":\"" + DictionaryId + "\"}}");
            if (call.Path == "/v2/streams/aliases")
            {
                var request = (Dictionary<string, object>)MiniJson.Parse(call.Body);
                AliasEpoch = (string)request["alias_epoch"];
                AliasCount = int.Parse(((JsonNumber)request["start"]).Lexeme) + ((List<object>)request["records"]).Count;
                return Json(200, "{\"server_time\":\"t\",\"alias_epoch\":\"" + AliasEpoch + "\",\"alias_count\":" + AliasCount + "}");
            }
            if (call.Path.StartsWith("/v2/assets/catalog/")) return new V7Response(200, Catalog, null);
            if (call.Path.StartsWith("/v2/assets/dictionary/")) return new V7Response(200, Dictionary, null);
            if (call.Path == "/v2/events/packet")
                return Json(200, "{\"server_time\":\"t\",\"accepted_count\":1,\"duplicate_count\":0,\"rejected\":[],\"ack_through\":" + Ack() + ",\"missing\":[],\"client_policy\":{\"mode\":\"active\",\"next_check_seconds\":3600,\"discard_pending\":false}}");
            return Error(404, "not_found");
        }
    }
}
