using System;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace Daliys.Analytics.Internal.Transport
{
    internal sealed class V8Settings
    {
        internal string ProjectId, SdkName, SdkVersion, AppVersion, BuildNumber, Platform;
        internal bool IntegerModel = true, StringModel = true;
        /// <summary>How long V8 stays off after the server reports it does not do V8 (no keys, no routes).</summary>
        internal TimeSpan UnavailableFor = TimeSpan.FromHours(1);
        internal Func<DateTimeOffset> Clock = () => DateTimeOffset.UtcNow;
        internal Func<byte[], IM7Compressor> CompressorFactory = dictionary => new NativeZstdCompressor(dictionary);
        internal Func<byte[]> RandomBytes = () => { var b = new byte[16]; using (var rng = RandomNumberGenerator.Create()) rng.GetBytes(b); return b; };
    }

    /// <summary>
    /// Client side of the V8 transport (docs/v8-transport.md in the server repository). It keeps a token, the project's shape table and the counts of what
    /// the server holds in the queue's durable key/value storage, so a normal launch sends its first packet straight away; only a missing token, a
    /// stream the server does not know, or a conflict makes it say hello. Whatever it cannot do, the caller sends through V1 instead.
    /// Single-threaded (the worker thread).
    /// </summary>
    internal sealed class V8Session : IDisposable
    {
        private const int MaxAttempts = 6, DisableAfterFailures = 3, MaxNoProgress = 3;
        private const string KeyToken = "v8.token", KeyNonce = "v8.nonce", KeyShapes = "v8.shapes", KeyServerShapes = "v8.sh", KeyServerAliases = "v8.al",
            KeyDictionary = "v8.dict", KeyPolicyVersion = "v8.p", KeyPolicy = "v8.pol";
        private const string NoDictionary = "0000000000000000";

        private readonly V8Settings _settings;
        private readonly IV7Http _http;
        private readonly IV7AssetStore _store;
        private readonly M8Shapes _shapes = new M8Shapes();
        private readonly M8Aliases _aliases = new M8Aliases();
        private M8Encoder _encoder;
        private bool _loaded;
        private string _token = "", _nonce = "", _dictionaryId = NoDictionary;
        private byte[] _dictionary;
        private long _epoch;
        private int _serverShapes, _serverAliases;
        private long _policyVersion = -1;
        private string _policyMode = "active";
        private long _policyNextCheck = 21600;
        private bool _policyDiscard;
        private bool _needHello, _newEpoch, _disabled;
        private int _consecutiveFailures, _noProgress, _tokenResets;
        private DateTimeOffset _unavailableUntil = DateTimeOffset.MinValue;

        internal V8Session(V8Settings settings, IV7Http http, IV7AssetStore store)
        {
            _settings = settings ?? throw new ArgumentNullException(nameof(settings));
            _http = http ?? throw new ArgumentNullException(nameof(http));
            _store = store ?? throw new ArgumentNullException(nameof(store));
        }

        internal bool Disabled => _disabled;
        internal string LastFallbackReason { get; private set; }
        internal string Token => _token;
        internal long Epoch => _epoch;
        internal int ServerShapes => _serverShapes;
        internal int ServerAliases => _serverAliases;
        internal int ShapeCount => _shapes.Count;

        /// <summary>Sends the oldest queued batch as one packet. <paramref name="readBatch"/> returns the queue's rows (called once the stream is ready).</summary>
        internal V7SendResult Send(IAnalyticsQueueBridge queue, Func<QueueBatch> readBatch)
        {
            if (_disabled) return Fallback("V8 is disabled for this process");
            if (_settings.Clock() < _unavailableUntil) return Fallback(LastFallbackReason ?? "V8 is not available");
            try
            {
                for (var attempt = 0; attempt < MaxAttempts; attempt++)
                {
                    var early = Prepare(queue, out var again);
                    if (early != null) return early;
                    if (again) continue;

                    var batch = readBatch();
                    if (batch == null || batch.Count == 0) return V7SendResult.Empty;
                    var sequence = MiniJson.ParseObject(queue.GetSequenceState());
                    var info = StreamInfo(sequence);
                    var encoded = _encoder.Encode(batch, info);
                    if (!encoded.Ok)
                    {
                        // a shape the server would not take must not stay in the table, or every later packet would carry it again
                        _shapes.TruncateTo(_serverShapes);
                        return Fallback(encoded.Failure);
                    }
                    var response = _http.PostBinary("/v3/packet", encoded.Frame, "application/vnd.mortris.m8", _token);
                    var outcome = Interpret(queue, response, encoded, out again);
                    if (again) continue;
                    if (outcome.Kind == V7ResultKind.Delivered) _consecutiveFailures = 0;
                    return outcome;
                }
                return Fallback("V8 could not settle after " + MaxAttempts + " attempts");
            }
            catch (Exception error) when (error is DllNotFoundException || error is EntryPointNotFoundException || error is BadImageFormatException)
            {
                _disabled = true;
                return Fallback("native zstd is unavailable: " + error.GetType().Name);
            }
        }

        public void Dispose()
        {
            _encoder?.Dispose();
            _encoder = null;
        }

        // --- state ---------------------------------------------------------------------------------------------

        private void Load(IAnalyticsQueueBridge queue)
        {
            _loaded = true;
            _token = queue.GetMeta(KeyToken);
            _nonce = queue.GetMeta(KeyNonce);
            if (string.IsNullOrEmpty(_nonce))
            {
                _nonce = NewNonce();
                queue.SetMeta(KeyNonce, _nonce);
            }
            if (!string.IsNullOrEmpty(queue.GetMeta(KeyShapes)) && !_shapes.TryLoad(queue.GetMeta(KeyShapes), _settings.ProjectId)) _shapes.Clear();
            _serverShapes = Math.Min(ToInt(queue.GetMeta(KeyServerShapes)), _shapes.Count);
            _serverAliases = ToInt(queue.GetMeta(KeyServerAliases));
            _dictionaryId = string.IsNullOrEmpty(queue.GetMeta(KeyDictionary)) ? NoDictionary : queue.GetMeta(KeyDictionary);
            long.TryParse(queue.GetMeta(KeyPolicyVersion), NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out _policyVersion);
            if (queue.GetMeta(KeyPolicyVersion) == "") _policyVersion = -1;
            var policy = queue.GetMeta(KeyPolicy).Split('|');
            if (policy.Length == 3 && long.TryParse(policy[1], NumberStyles.None, CultureInfo.InvariantCulture, out var next)) { _policyMode = policy[0]; _policyNextCheck = next; _policyDiscard = policy[2] == "1"; }
            var sequence = MiniJson.ParseObject(queue.GetSequenceState());
            _epoch = ToLong(sequence["stream_epoch"]);
            _aliases.Reset(_serverAliases);
            _needHello = string.IsNullOrEmpty(_token) || _epoch == 0;
        }

        private void Persist(IAnalyticsQueueBridge queue)
        {
            queue.SetMeta(KeyToken, _token);
            queue.SetMeta(KeyShapes, _shapes.ToJson(_settings.ProjectId, _serverShapes));
            queue.SetMeta(KeyServerShapes, _serverShapes.ToString(CultureInfo.InvariantCulture));
            queue.SetMeta(KeyServerAliases, _serverAliases.ToString(CultureInfo.InvariantCulture));
            queue.SetMeta(KeyDictionary, _dictionaryId);
        }

        private string NewNonce() => Convert.ToBase64String(_settings.RandomBytes()).TrimEnd('=').Replace('+', '-').Replace('/', '_');

        private static int ToInt(string text) => int.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out var value) ? value : 0;

        private M8StreamInfo StreamInfo(Dictionary<string, object> sequence)
        {
            var dropped = new List<KeyValuePair<long, long>>();
            foreach (List<object> range in (List<object>)sequence["dropped"]) dropped.Add(new KeyValuePair<long, long>(ToLong(range[0]), ToLong(range[1])));
            return new M8StreamInfo
            {
                Epoch = _epoch, SentAtMs = _settings.Clock().ToUnixTimeMilliseconds(), StreamBase = ToLong(sequence["stream_base"]),
                HighWater = ToLong(sequence["next_sequence"]) - 1, ServerShapes = _serverShapes, ServerAliases = _serverAliases, Dropped = dropped,
            };
        }

        // --- hello, assets -----------------------------------------------------------------------------------------

        /// <summary>Makes the session ready to send. Returns a result when the send must stop; <paramref name="again"/> asks the caller to run the attempt once more.</summary>
        private V7SendResult Prepare(IAnalyticsQueueBridge queue, out bool again)
        {
            again = false;
            if (!_loaded) Load(queue);
            if (_needHello)
            {
                var early = Hello(queue);
                if (early != null) return early;
                again = _needHello;       // a hello that must be repeated (token reset, new epoch)
                if (again) return null;
            }
            if (_encoder == null)
            {
                var early = BuildEncoder(queue);
                if (early != null) return early;
            }
            return null;
        }

        private V7SendResult Hello(IAnalyticsQueueBridge queue)
        {
            var sequence = MiniJson.ParseObject(queue.GetSequenceState());
            var queueEpoch = ToLong(sequence["stream_epoch"]);
            if (queueEpoch == 0 || _newEpoch)
            {
                if (queueEpoch == 0) queue.BeginNewStream();   // rows below the lowest queued one were delivered or dropped before the stream existed
                sequence = MiniJson.ParseObject(queue.GetSequenceState());
            }
            var openNew = _newEpoch || _epoch == 0 || queueEpoch == 0;
            var body = new StringBuilder();
            body.Append("{\"v\":3,\"project_id\":").Append(MiniJson.Escape(_settings.ProjectId));
            if (string.IsNullOrEmpty(_token)) body.Append(",\"nonce\":").Append(MiniJson.Escape(_nonce));
            body.Append(",\"sdk\":").Append(MiniJson.Escape(_settings.SdkName + "/" + _settings.SdkVersion))
                .Append(",\"app_version\":").Append(MiniJson.Escape(_settings.AppVersion ?? ""))
                .Append(",\"build_number\":").Append(MiniJson.Escape(_settings.BuildNumber ?? ""))
                .Append(",\"platform\":").Append(MiniJson.Escape(_settings.Platform ?? "unknown"))
                .Append(",\"epoch\":").Append((openNew ? 0 : _epoch).ToString(CultureInfo.InvariantCulture))
                .Append(",\"stream\":{\"base\":").Append(ToLong(sequence["stream_base"]).ToString(CultureInfo.InvariantCulture))
                .Append(",\"high\":").Append((ToLong(sequence["next_sequence"]) - 1).ToString(CultureInfo.InvariantCulture))
                .Append(",\"dropped\":[");
            var first = true;
            foreach (List<object> range in (List<object>)sequence["dropped"])
            {
                if (!first) body.Append(',');
                first = false;
                body.Append('[').Append(ToLong(range[0]).ToString(CultureInfo.InvariantCulture)).Append(',').Append(ToLong(range[1]).ToString(CultureInfo.InvariantCulture)).Append(']');
            }
            body.Append("]}}");

            var response = _http.PostJson("/v3/hello", body.ToString(), string.IsNullOrEmpty(_token) ? null : _token);
            if (response.Status == 401)
            {
                // the token is not good (key retired, installation revoked): register again; a second refusal in a row means the nonce itself maps to a bad installation
                _token = "";
                queue.SetMeta(KeyToken, "");
                if (++_tokenResets > 1) { _nonce = NewNonce(); queue.SetMeta(KeyNonce, _nonce); _tokenResets = 0; }
                return null;               // the same stream is re-synchronized under the new token (or the server says it does not know it)
            }
            if (IsTransient(response.Status)) return V7SendResult.Retry(response.Status, response.RetryAfter, "hello: " + response.Status);
            if (response.Status == 409 && (response.ErrorCode == "stream_rollback" || response.ErrorCode == "stream_conflict") || response.Status == 404 && response.ErrorCode == "unknown_stream")
            {
                queue.BeginNewStream();                 // the server saw a higher sequence than this client has, or does not know the stream: continue under a new epoch
                _newEpoch = true;
                return null;
            }
            if (!response.IsSuccess)
            {
                MarkUnavailable("hello answered " + response.Status + " " + response.ErrorCode);
                return Fallback(LastFallbackReason);
            }

            var result = MiniJson.ParseObject(response.Text);
            var token = (string)result["token"];
            var epoch = ToLong(result["epoch"]);
            if (string.IsNullOrEmpty(token) || epoch < 1) throw new FormatException("hello returned no token or epoch");
            _token = token;
            _tokenResets = 0;
            // the installation's V1 identity: a batch this session has to leave to V1 then belongs to the same installation and carries the ids the server derives
            if (result.TryGetValue("install", out var install) && install is string installId && result.TryGetValue("credential", out var credential) && credential is string credentialText)
                queue.AdoptIdentity(installId, credentialText);
            if (epoch != queueEpoch) queue.SetStreamEpoch(epoch);
            _epoch = epoch;
            _newEpoch = false;
            var ack = ToLong(result["ack"]);
            if (ack > 0) queue.DeleteThroughSequence(ack);
            _serverShapes = (int)ToLong(result["shapes"]);
            _serverAliases = (int)ToLong(result["aliases"]);
            _aliases.Reset(_serverAliases);
            _encoder?.Dispose();
            _encoder = null;

            var catalogId = (string)result["catalog"];
            var dictionaryId = (string)result["dict"];
            // the local shape table must agree with the server's on the shapes the server holds; otherwise adopt the server's
            if (_serverShapes > _shapes.Count || (_serverShapes > 0 && _shapes.CatalogId(_settings.ProjectId, _serverShapes) != catalogId))
            {
                var fetched = AdoptCatalog();
                if (fetched != null) return fetched;
            }
            if (dictionaryId != _dictionaryId) { _dictionaryId = dictionaryId; _dictionary = null; }
            _needHello = false;
            Persist(queue);
            return null;
        }

        private V7SendResult AdoptCatalog()
        {
            var response = _http.Get("/v3/catalog", _token);
            if (response.Status == 401) { _token = ""; _needHello = true; return V7SendResult.Retry(401, null, "catalog: token refused"); }
            if (IsTransient(response.Status)) return V7SendResult.Retry(response.Status, response.RetryAfter, "catalog: " + response.Status);
            if (!response.IsSuccess || !_shapes.TryLoad(response.Text, _settings.ProjectId))
            {
                MarkUnavailable("the project's catalog could not be fetched or is unusable (" + response.Status + ")");
                return Fallback(LastFallbackReason);
            }
            if (_shapes.Count < _serverShapes) { MarkUnavailable("the catalog is shorter than the server reported"); return Fallback(LastFallbackReason); }
            _serverShapes = _shapes.Count;
            return null;
        }

        private V7SendResult BuildEncoder(IAnalyticsQueueBridge queue)
        {
            if (_dictionaryId != NoDictionary && _dictionary == null)
            {
                _dictionary = _store.TryRead("dictionary", _dictionaryId);
                if (_dictionary == null || AssetId(_dictionary) != _dictionaryId)
                {
                    var response = _http.Get("/v3/assets/dictionary/" + _dictionaryId, _token);
                    if (response.Status == 401) { _token = ""; _needHello = true; return V7SendResult.Retry(401, null, "dictionary: token refused"); }
                    if (IsTransient(response.Status)) return V7SendResult.Retry(response.Status, response.RetryAfter, "dictionary: " + response.Status);
                    if (!response.IsSuccess || AssetId(response.Body) != _dictionaryId)
                    {
                        // without the dictionary packets would not decode: stay on no dictionary until the next hello announces a usable one
                        _dictionary = null; _dictionaryId = NoDictionary;
                    }
                    else
                    {
                        _dictionary = response.Body;
                        _store.Write("dictionary", _dictionaryId, _dictionary);
                    }
                }
            }
            _encoder = new M8Encoder(_shapes, _aliases, _dictionaryId == NoDictionary ? null : _dictionary, _settings.CompressorFactory(_dictionaryId == NoDictionary ? null : _dictionary),
                _settings.SdkName + "/" + _settings.SdkVersion, _settings.IntegerModel, _settings.StringModel);
            return null;
        }

        private static string AssetId(byte[] data)
        {
            using (var sha = SHA256.Create())
            {
                var hash = sha.ComputeHash(data);
                var builder = new StringBuilder(16);
                for (var i = 0; i < 8; i++) builder.Append(hash[i].ToString("x2", CultureInfo.InvariantCulture));
                return builder.ToString();
            }
        }

        // --- packets -------------------------------------------------------------------------------------------------

        private V7SendResult Interpret(IAnalyticsQueueBridge queue, V7Response response, M7EncodeResult encoded, out bool again)
        {
            again = false;
            var status = response.Status;
            if (status == 401)
            {
                _token = ""; _needHello = true; again = true;
                return null;
            }
            if (status == 413 || (status == 400 && response.ErrorCode == "invalid_batch_size")) return new V7SendResult { Kind = V7ResultKind.PayloadTooLarge, Status = status };
            if (IsTransient(status) && status != 503) return V7SendResult.Retry(status, response.RetryAfter, "packet: " + status);
            if (status == 503 && response.ErrorCode == "transport_unavailable") { MarkUnavailable("the server has no V8 keys"); return Fallback(LastFallbackReason); }
            if (status == 503) return V7SendResult.Retry(status, response.RetryAfter, "packet: " + status);
            if (status == 404 && response.ErrorCode == "unknown_stream") { queue.BeginNewStream(); _newEpoch = true; _needHello = true; again = true; return null; }
            if (status == 404) { MarkUnavailable("this server has no V8 routes"); return Fallback(LastFallbackReason); }
            if (status == 409)
            {
                switch (response.ErrorCode)
                {
                    case "stream_rollback":
                    case "stream_conflict":
                    case "alias_conflict":
                        queue.BeginNewStream(); _newEpoch = true; _needHello = true; again = true; return null;
                    case "shapes_missing":
                    {
                        var held = DetailCount(response.Text, "shapes");
                        _serverShapes = Math.Max(0, Math.Min(held, _shapes.Count));
                        if (held > _shapes.Count) { var fetched = AdoptCatalog(); if (fetched != null) return fetched; }
                        again = true; return null;
                    }
                    case "aliases_missing":
                    {
                        var held = DetailCount(response.Text, "aliases");
                        if (held < _aliases.Base) { _newEpoch = true; _needHello = true; queue.BeginNewStream(); }   // the server lost slots this process builds on
                        else _serverAliases = held;
                        again = true; return null;
                    }
                    case "shape_conflict":
                    {
                        // another installation registered a different shape at that position first: take the server's table and re-resolve
                        var fetched = AdoptCatalog();
                        if (fetched != null) return fetched;
                        again = true; return null;
                    }
                    case "transport_assets_unknown":
                        _dictionaryId = NoDictionary; _dictionary = null; _encoder?.Dispose(); _encoder = null; again = true; return null;
                }
            }
            if (status == 422)
            {
                _shapes.TruncateTo(_serverShapes);       // the server will not take this shape; do not carry it into later packets
                return Fallback("packet answered 422 " + response.ErrorCode);
            }
            if (!response.IsSuccess)
            {
                if (++_consecutiveFailures >= DisableAfterFailures) _disabled = true;
                return Fallback("packet answered " + status + " " + response.ErrorCode);
            }

            var result = MiniJson.ParseObject(response.Text);
            var ack = ToLong(result["ack"]);
            var removed = queue.DeleteThroughSequence(ack);
            if (result.TryGetValue("dict", out var announced) && announced is string newDictionary && newDictionary.Length == 16 && newDictionary != _dictionaryId)
            {
                // a dictionary was trained since the last hello: use it from the next packet (its bytes are fetched when the encoder is rebuilt)
                _dictionaryId = newDictionary; _dictionary = null;
                _encoder?.Dispose(); _encoder = null;
            }
            // the server holds what the frame carried now
            _serverShapes = encoded.ShapeCount;
            _serverAliases = encoded.AliasCount;
            Persist(queue);
            if (removed == 0)
            {
                // The server settled nothing we hold: an earlier number is still open. Never loop on the same batch; after a few rounds give V8 a rest.
                if (++_noProgress >= MaxNoProgress)
                {
                    _noProgress = 0;
                    MarkUnavailable("V8 acknowledged through " + ack + " without settling any queued event");
                    return Fallback(LastFallbackReason);
                }
                return V7SendResult.Retry(200, null, "packet acknowledged through " + ack + " but removed no queued event");
            }
            _noProgress = 0;
            var p = result.TryGetValue("p", out var pv) ? ToLong(pv) : _policyVersion;
            if (p != _policyVersion)
            {
                var fetched = FetchPolicy(queue, p);
                if (fetched != null) return fetched;
            }
            return new V7SendResult
            {
                Kind = V7ResultKind.Delivered, Removed = removed, PolicyMode = _policyMode, DiscardPending = _policyDiscard, NextCheckSeconds = (int)_policyNextCheck,
            };
        }

        private V7SendResult FetchPolicy(IAnalyticsQueueBridge queue, long p)
        {
            var response = _http.Get("/v3/policy", _token);
            if (!response.IsSuccess) return null;        // keep the old policy; the next packet's p will ask again
            var policy = MiniJson.ParseObject(response.Text);
            var mode = (string)policy["mode"];
            if (mode != "active" && mode != "pause_upload" && mode != "disable_collection") throw new FormatException("unknown client policy mode");
            _policyMode = mode;
            _policyNextCheck = ToLong(policy["next_check_seconds"]);
            _policyDiscard = policy["discard_pending"] is bool discard && discard;
            _policyVersion = ToLong(policy["p"]);
            queue.SetMeta(KeyPolicyVersion, _policyVersion.ToString(CultureInfo.InvariantCulture));
            queue.SetMeta(KeyPolicy, _policyMode + "|" + _policyNextCheck.ToString(CultureInfo.InvariantCulture) + "|" + (_policyDiscard ? "1" : "0"));
            return null;
        }

        // --- helpers -----------------------------------------------------------------------------------------------------

        private static int DetailCount(string body, string key)
        {
            try
            {
                var root = MiniJson.ParseObject(body);
                return root.TryGetValue("details", out var d) && d is Dictionary<string, object> details && details.TryGetValue(key, out var v) ? (int)ToLong(v) : 0;
            }
            catch (Exception) { return 0; }
        }

        private V7SendResult Fallback(string reason) { LastFallbackReason = reason; return V7SendResult.Fallback(reason); }

        private void MarkUnavailable(string reason)
        {
            LastFallbackReason = reason;
            _unavailableUntil = _settings.Clock() + _settings.UnavailableFor;
        }

        private static bool IsTransient(int status) => status == 408 || status == 429 || status >= 500 || status == 0;

        private static long ToLong(object value)
        {
            if (value is JsonNumber number && long.TryParse(number.Lexeme, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var result)) return result;
            throw new FormatException("integer expected");
        }
    }
}
