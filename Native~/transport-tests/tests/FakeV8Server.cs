using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Daliys.Analytics.Internal.Transport;

namespace M7Transport.Tests
{
    /// <summary>
    /// A model of the V8 server (docs/v8-transport.md) that understands frame headers, sections and the sequence column, but not the property columns:
    /// enough to exercise V8Session's whole conversation (hello, tokens, shape and alias tables, acknowledgement, every error the contract defines).
    /// The real server is exercised by the end-to-end test against the Go implementation.
    /// </summary>
    internal sealed class FakeV8Server : IV7Http
    {
        internal sealed class Stream
        {
            internal long Base, High;
            internal readonly SortedSet<long> Received = new SortedSet<long>(), Dropped = new SortedSet<long>();
            internal readonly List<string> Aliases = new List<string>();
        }

        internal readonly List<Call> Calls = new List<Call>();
        internal Func<Call, V7Response> Override;
        internal readonly Dictionary<string, long> InstallsByNonce = new Dictionary<string, long>();
        internal readonly Dictionary<long, Dictionary<long, Stream>> Streams = new Dictionary<long, Dictionary<long, Stream>>();
        internal readonly List<string> ShapeSignatures = new List<string>();
        internal readonly List<string> ShapeJson = new List<string>();
        internal readonly HashSet<long> Revoked = new HashSet<long>();
        internal string DictionaryId = "0000000000000000";
        internal byte[] Dictionary;
        internal long PolicyVersion = 1000;
        internal string PolicyMode = "active";
        internal bool Strict;
        internal int MaxPacketRows = 500;
        internal string KeyVersion = "k";
        internal readonly List<long> StoredSequences = new List<long>();
        internal readonly List<int> ShapeSectionSizes = new List<int>();
        internal readonly List<int> AliasSectionSizes = new List<int>();
        internal readonly string Project;
        private long _nextInstall = 1;

        internal FakeV8Server(string project) { Project = project; }

        internal string Token(long id) => id.ToString(CultureInfo.InvariantCulture) + "." + KeyVersion + "TAG" + id.ToString("D8", CultureInfo.InvariantCulture);

        private long Authenticate(string credential)
        {
            if (string.IsNullOrEmpty(credential)) return -1;
            var parts = credential.Split('.');
            if (parts.Length != 2 || !long.TryParse(parts[0], out var id) || credential != Token(id) || !Streams.ContainsKey(id) && !InstallsByNonce.ContainsValue(id)) return -1;
            return id;
        }

        private V7Response Record(string method, string path, string body, byte[] packet, string credential)
        {
            var call = new Call { Method = method, Path = path, Body = body, Packet = packet, Credential = credential };
            Calls.Add(call);
            return Override?.Invoke(call) ?? Handle(call);
        }

        public V7Response PostJson(string path, string json, string credential) => Record("POST", path, json, null, credential);
        public V7Response PutJson(string path, string json, string credential) => Record("PUT", path, json, null, credential);
        public V7Response PostPacket(string path, byte[] packet, IReadOnlyDictionary<string, string> headers, string credential) => Record("POST", path, null, packet, credential);
        public V7Response PostBinary(string path, byte[] body, string contentType, string credential) => Record("POST", path, null, body, credential);
        public V7Response Get(string pathAndQuery, string credential) => Record("GET", pathAndQuery, null, null, credential);

        internal static V7Response Json(int status, string body) => new V7Response(status, Encoding.UTF8.GetBytes(body), null);
        internal static V7Response Error(int status, string code, string details = null) =>
            Json(status, "{\"server_time\":\"t\",\"code\":\"" + code + "\",\"message\":\"m\",\"request_id\":\"r\"" + (details == null ? "" : ",\"details\":" + details) + "}");

        internal string CatalogDocument()
        {
            var json = new StringBuilder("{\"project_id\":" + MiniJson.Escape(Project) + ",\"shapes\":[");
            json.Append(string.Join(",", ShapeJson));
            return json.Append("]}").ToString();
        }

        internal string CatalogId()
        {
            using (var sha = SHA256.Create())
            {
                var h = sha.ComputeHash(Encoding.UTF8.GetBytes(CatalogDocument()));
                return string.Concat(h.Take(8).Select(b => b.ToString("x2")));
            }
        }

        private V7Response Handle(Call call)
        {
            if (call.Path == "/v3/hello") return Hello(call);
            if (call.Path == "/v3/packet") return Packet(call);
            var id = Authenticate(call.Credential);
            if (call.Path == "/v3/policy")
                return id < 0 ? Error(401, "token_invalid") : Json(200, "{\"mode\":\"" + PolicyMode + "\",\"next_check_seconds\":21600,\"discard_pending\":false,\"p\":" + PolicyVersion + "}");
            if (call.Path == "/v3/catalog") return id < 0 ? Error(401, "token_invalid") : Json(200, CatalogDocument());
            if (call.Path.StartsWith("/v3/assets/dictionary/", StringComparison.Ordinal))
                return id < 0 ? Error(401, "token_invalid") : Dictionary != null && call.Path.EndsWith(DictionaryId) ? new V7Response(200, Dictionary, null) : Error(409, "transport_assets_unknown");
            return Error(404, "not_found");
        }

        private V7Response Hello(Call call)
        {
            var request = MiniJson.ParseObject(call.Body);
            long id;
            if (string.IsNullOrEmpty(call.Credential))
            {
                var nonce = (string)request["nonce"];
                if (!InstallsByNonce.TryGetValue(nonce, out id)) { id = _nextInstall++; InstallsByNonce[nonce] = id; Streams[id] = new Dictionary<long, Stream>(); }
            }
            else if ((id = Authenticate(call.Credential)) < 0) return Error(401, "token_invalid");
            if (Revoked.Contains(id)) return Error(401, "token_revoked");
            var epoch = Num(request["epoch"]);
            var stream = (Dictionary<string, object>)request["stream"];
            var streams = Streams[id];
            if (epoch == 0) epoch = streams.Count == 0 ? 1 : (call.Credential == null && streams.Count > 0 ? streams.Keys.Max() : streams.Keys.Max() + 1);
            if (!streams.TryGetValue(epoch, out var s))
            {
                if (Num(request["epoch"]) != 0) return Error(404, "unknown_stream");
                streams[epoch] = s = new Stream { Base = Num(stream["base"]) };
            }
            else
            {
                if (Num(stream["base"]) != s.Base) return Error(409, "stream_conflict");
                if (Num(stream["high"]) < s.High) return Error(409, "stream_rollback");
            }
            s.High = Math.Max(s.High, Num(stream["high"]));
            foreach (List<object> d in (List<object>)stream["dropped"]) for (var n = Num(d[0]); n <= Num(d[1]); n++) s.Dropped.Add(n);
            return Json(200, "{\"token\":\"" + Token(id) + "\",\"epoch\":" + epoch + ",\"ack\":" + Ack(s) + ",\"missing\":[],\"shapes\":" + ShapeSignatures.Count + ",\"aliases\":" + s.Aliases.Count +
                             ",\"catalog\":\"" + CatalogId() + "\",\"dict\":\"" + DictionaryId + "\",\"p\":" + PolicyVersion + ",\"install\":\"" + InstallUuid(id) + "\",\"credential\":\"" + new string('c', 43) + "\"}");
        }

        internal static string InstallUuid(long id) => "6f1c9b0e-2d44-4f6a-9a31-" + id.ToString("D12", CultureInfo.InvariantCulture);

        internal static long Num(object o) => long.Parse(((JsonNumber)o).Lexeme, CultureInfo.InvariantCulture);

        internal static long Ack(Stream s)
        {
            var n = s.Base - 1;
            while (s.Received.Contains(n + 1) || s.Dropped.Contains(n + 1)) n++;
            return n;
        }

        // --- frame -----------------------------------------------------------------------------------------------

        private sealed class FrameReader
        {
            private readonly byte[] _b; internal int P;
            internal FrameReader(byte[] b) { _b = b; }
            internal ulong U() { ulong v = 0; var shift = 0; while (true) { var x = _b[P++]; v |= (ulong)(x & 127) << shift; if (x < 128) return v; shift += 7; } }
            internal string Text() { var n = (int)U(); var s = Encoding.UTF8.GetString(_b, P, n); P += n; return s; }
            internal byte Byte() => _b[P++];
            internal byte[] Take(int n) { var r = new byte[n]; Buffer.BlockCopy(_b, P, r, 0, n); P += n; return r; }
            internal long Zig() { var u = U(); return (long)(u >> 1) ^ -(long)(u & 1); }
        }

        private V7Response Packet(Call call)
        {
            var id = Authenticate(call.Credential);
            if (id < 0) return Error(401, "token_invalid");
            if (Revoked.Contains(id)) return Error(401, "token_revoked");
            var f = call.Packet;
            if (f.Length < 20 || f[0] != 'M' || f[1] != '8' || M7FrameEncoder.Crc(f, f.Length - 4) != BitConverter.ToUInt32(f, f.Length - 4)) return Error(400, "invalid_packet");
            var r = new FrameReader(f) { P = 2 };
            var flags = r.Byte();
            var dictionary = string.Concat(r.Take(8).Select(b => b.ToString("x2")));
            var epoch = (long)r.U(); r.U(); var streamBase = (long)r.U(); var high = (long)r.U(); var shapeCount = (int)r.U(); var aliasCount = (int)r.U();
            var newAliases = new List<string>(); var aliasStart = 0;
            if ((flags & 8) != 0)
            {
                aliasStart = (int)r.U(); var n = (int)r.U();
                for (var i = 0; i < n; i++)
                {
                    var rec = new StringBuilder(BitConverter.ToString(r.Take(16)));
                    for (var j = 0; j < 7; j++) rec.Append('|').Append(r.Text());
                    rec.Append('|').Append(r.Zig());
                    newAliases.Add(rec.ToString());
                }
            }
            var newShapes = new List<KeyValuePair<string, string>>(); var shapeStart = 0;
            if ((flags & 16) != 0)
            {
                shapeStart = (int)r.U(); var n = (int)r.U();
                for (var i = 0; i < n; i++)
                {
                    var name = r.Text(); var fields = (int)r.U(); var sig = new StringBuilder(name); var fj = new StringBuilder();
                    for (var j = 0; j < fields; j++)
                    {
                        var key = r.Text(); var kind = r.Byte();
                        sig.Append('|').Append(key).Append(':').Append(kind);
                        if (j > 0) fj.Append(',');
                        fj.Append('[').Append(MiniJson.Escape(key)).Append(',').Append(kind).Append(']');
                    }
                    newShapes.Add(new KeyValuePair<string, string>(sig.ToString(), "[" + MiniJson.Escape(name) + ",[" + fj + "]]"));
                }
            }
            var dropped = new List<KeyValuePair<long, long>>();
            if ((flags & 32) != 0) { var n = (int)r.U(); for (var i = 0; i < n; i++) dropped.Add(new KeyValuePair<long, long>((long)r.U(), (long)r.U())); }
            var count = (int)r.U(); var rawSize = (int)r.U();
            if (count > MaxPacketRows) return Error(400, "invalid_batch_size");
            if (!Streams.TryGetValue(id, out var streams) || !streams.TryGetValue(epoch, out var stream)) return Error(404, "unknown_stream");
            if (streamBase != stream.Base) return Error(409, "stream_conflict");
            if (high < stream.High) return Error(409, "stream_rollback");
            var details = "{\"shapes\":" + ShapeSignatures.Count + ",\"aliases\":" + stream.Aliases.Count + ",\"catalog\":\"" + CatalogId() + "\"}";
            // shapes
            var shapes = new List<string>(ShapeSignatures); var shapeJson = new List<string>(ShapeJson);
            for (var i = 0; i < newShapes.Count; i++)
            {
                var position = shapeStart + i;
                if (position < shapes.Count) { if (shapes[position] != newShapes[i].Key) return Error(409, "shape_conflict", details); }
                else if (position == shapes.Count) { if (Strict) return Error(422, "shape_not_allowed"); shapes.Add(newShapes[i].Key); shapeJson.Add(newShapes[i].Value); }
                else return Error(409, "shapes_missing", details);
            }
            var aliases = new List<string>(stream.Aliases);
            for (var i = 0; i < newAliases.Count; i++)
            {
                var position = aliasStart + i;
                if (position < aliases.Count) { if (aliases[position] != newAliases[i]) return Error(409, "alias_conflict"); }
                else if (position == aliases.Count) aliases.Add(newAliases[i]);
                else return Error(409, "aliases_missing", details);
            }
            if (shapeCount > shapes.Count) return Error(409, "shapes_missing", "{\"shapes\":" + shapes.Count + ",\"aliases\":" + aliases.Count + ",\"catalog\":\"" + CatalogId() + "\"}");
            if (aliasCount > aliases.Count) return Error(409, "aliases_missing", "{\"shapes\":" + shapes.Count + ",\"aliases\":" + aliases.Count + ",\"catalog\":\"" + CatalogId() + "\"}");
            if (dictionary != DictionaryId && dictionary != "0000000000000000") return Error(409, "transport_assets_unknown");
            // the body (uncompressed in these tests): the first integer column is the sequence
            var body = f.Skip(r.P).Take(f.Length - 4 - r.P).ToArray();
            var sequences = ReadInts(body, count);
            ShapeSignatures.Clear(); ShapeSignatures.AddRange(shapes); ShapeJson.Clear(); ShapeJson.AddRange(shapeJson);
            stream.Aliases.Clear(); stream.Aliases.AddRange(aliases);
            ShapeSectionSizes.Add(newShapes.Count); AliasSectionSizes.Add(newAliases.Count);
            foreach (var range in dropped) for (var n = range.Key; n <= range.Value; n++) stream.Dropped.Add(n);
            stream.High = Math.Max(stream.High, high);
            foreach (var s in sequences) { stream.Received.Add(s); StoredSequences.Add(s); }
            return Json(200, "{\"ack\":" + Ack(stream) + ",\"p\":" + PolicyVersion + (dictionary != DictionaryId ? ",\"dict\":\"" + DictionaryId + "\"" : "") + "}");
        }

        /// <summary>Decodes the first integer column (mode 0 or 1: varints, direct or delta; mode 2 or 3: bit-packed).</summary>
        internal static long[] ReadInts(byte[] raw, int n)
        {
            var r = new FrameReader(raw);
            var mode = r.Byte();
            var values = new long[n];
            if (mode < 2) for (var i = 0; i < n; i++) values[i] = r.Zig();
            else
            {
                var lo = r.Zig(); var width = r.Byte();
                var data = r.Take((n * width + 7) / 8);
                for (var i = 0; i < n; i++)
                {
                    ulong v = 0;
                    for (var j = 0; j < width; j++) { var bit = i * width + j; v |= (ulong)((data[bit / 8] >> (bit % 8)) & 1) << j; }
                    values[i] = lo + (long)v;
                }
            }
            if (mode == 1 || mode == 3) for (var i = 1; i < n; i++) values[i] += values[i - 1];
            return values;
        }
    }
}
