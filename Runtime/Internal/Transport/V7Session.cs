using System;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace Daliys.Analytics.Internal.Transport
{
    internal enum V7ResultKind { Delivered, Empty, Fallback, Retry, Unauthorized, PayloadTooLarge }

    internal sealed class V7SendResult
    {
        internal V7ResultKind Kind;
        /// <summary>Queued rows the acknowledgement removed.</summary>
        internal int Removed;
        internal string PolicyMode;
        internal int NextCheckSeconds;
        internal bool DiscardPending;
        internal int Status;
        internal TimeSpan? RetryAfter;
        internal string Detail;

        internal static V7SendResult Fallback(string detail) => new V7SendResult { Kind = V7ResultKind.Fallback, Detail = detail };
        internal static V7SendResult Retry(int status, TimeSpan? retryAfter, string detail) => new V7SendResult { Kind = V7ResultKind.Retry, Status = status, RetryAfter = retryAfter, Detail = detail };
        internal static readonly V7SendResult Empty = new V7SendResult { Kind = V7ResultKind.Empty };
        internal static V7SendResult Unauthorized() => new V7SendResult { Kind = V7ResultKind.Unauthorized, Status = 401 };
    }

    internal sealed class V7Settings
    {
        internal string ProjectId;
        internal string SdkName;
        internal string SdkVersion;
        internal bool IntegerModel = true, StringModel = true;
        /// <summary>How long V7 stays off after the server reports no V7 support for the project (or V7 made no progress).</summary>
        internal TimeSpan UnavailableFor = TimeSpan.FromHours(1);
        internal Func<DateTimeOffset> Clock = () => DateTimeOffset.UtcNow;
        internal Func<byte[], IM7Compressor> CompressorFactory = dictionary => new NativeZstdCompressor(dictionary);
    }

    /// <summary>
    /// Client side of the V7 transport (docs/v7-transport.md in the server repository): opens the sequence stream, keeps the
    /// catalog, dictionary and alias table in step with the server, sends packets, and settles the queue by sequence.
    /// It never blocks delivery: whatever it cannot do, the caller sends through V1 instead. Single-threaded (the worker thread).
    /// </summary>
    internal sealed class V7Session : IDisposable
    {
        private const int MaxAttempts = 4, AliasChunk = 500, DisableAfterFailures = 3, MaxNoProgress = 3;

        private readonly V7Settings _settings;
        private readonly IV7Http _http;
        private readonly IV7AssetStore _store;
        private M7EventEncoder _encoder;
        private M7Aliases _aliases;
        private string _installId;
        private string _loadedCatalogId = "", _loadedDictionaryId = "";
        private string _serverCatalogId = "", _serverDictionaryId = "";
        private int _aliasesUploaded;
        private long _streamEpoch;
        private long _syncedDroppedVersion = -1;
        private bool _forceSync;
        private bool _disabled;
        private int _consecutiveFailures, _noProgress;
        private DateTimeOffset _unavailableUntil = DateTimeOffset.MinValue;

        internal V7Session(V7Settings settings, IV7Http http, IV7AssetStore store)
        {
            _settings = settings ?? throw new ArgumentNullException(nameof(settings));
            _http = http ?? throw new ArgumentNullException(nameof(http));
            _store = store ?? throw new ArgumentNullException(nameof(store));
        }

        /// <summary>True when V7 gave up for this process (native library missing, repeated protocol failures).</summary>
        internal bool Disabled => _disabled;
        internal string LastFallbackReason { get; private set; }

        /// <summary>
        /// Sends the oldest queued batch as one packet. <paramref name="readBatch"/> is called after the stream is in sync (a sync may
        /// settle rows), and returns the queue's JSON array.
        /// </summary>
        internal V7SendResult Send(IAnalyticsQueueBridge queue, AnalyticsQueueState state, Func<string> readBatch)
        {
            if (_disabled) return Fallback("V7 is disabled for this process");
            if (_settings.Clock() < _unavailableUntil) return Fallback(LastFallbackReason ?? "V7 is not available");
            try
            {
                for (var attempt = 0; attempt < MaxAttempts; attempt++)
                {
                    var prepared = Prepare(queue, state, out var early);
                    if (early != null) return early;
                    if (!prepared) continue;

                    var batch = readBatch();
                    if (batch == null || batch.Length <= 2) return V7SendResult.Empty;
                    var encoded = _encoder.Encode(batch);
                    if (!encoded.Ok) return Fallback(encoded.Failure);

                    var aliases = UploadAliases(state, out var restart);
                    if (aliases != null) return aliases;
                    if (restart) continue;

                    var outcome = Interpret(queue, PostPacket(state, encoded), out var again);
                    if (again) continue;
                    if (outcome.Kind == V7ResultKind.Delivered) _consecutiveFailures = 0;
                    return outcome;
                }
                return Fallback("V7 could not settle after " + MaxAttempts + " attempts");
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

        // --- stream and assets --------------------------------------------------------------------------

        /// <summary>Makes the stream, assets and encoder ready. Returns false when the attempt must run again (or <paramref name="early"/> is set).</summary>
        private bool Prepare(IAnalyticsQueueBridge queue, AnalyticsQueueState state, out V7SendResult early)
        {
            early = null;
            if (_installId != state.InstallationId)
            {
                // A different installation (credential reset): nothing of the old stream, aliases or origin applies.
                _encoder?.Dispose();
                _encoder = null;
                _loadedCatalogId = _loadedDictionaryId = "";
                _installId = state.InstallationId;
                _syncedDroppedVersion = -1;
                _streamEpoch = 0;
                _aliasesUploaded = 0;
            }
            var sequence = MiniJson.ParseObject(queue.GetSequenceState());
            var epoch = ToLong(sequence["stream_epoch"]);
            var droppedVersion = ToLong(sequence["dropped_version"]);
            if (epoch == 0 || _forceSync || droppedVersion != _syncedDroppedVersion)
            {
                if (epoch == 0)
                {
                    queue.BeginNewStream();           // rows below the lowest queued one were delivered or dropped before the stream existed
                    sequence = MiniJson.ParseObject(queue.GetSequenceState());
                    droppedVersion = ToLong(sequence["dropped_version"]);
                }
                if (!Sync(queue, state, sequence, epoch, droppedVersion, out early)) return false;
            }
            if (_encoder == null)
            {
                early = LoadAssetsAndEncoder(state);
                if (early != null) return false;
            }
            return true;
        }

        private bool Sync(IAnalyticsQueueBridge queue, AnalyticsQueueState state, Dictionary<string, object> sequence, long epoch, long droppedVersion, out V7SendResult early)
        {
            early = null;
            var body = new StringBuilder();
            body.Append("{\"schema_version\":2,\"project_id\":").Append(MiniJson.Escape(_settings.ProjectId))
                .Append(",\"install_id\":").Append(MiniJson.Escape(state.InstallationId))
                .Append(",\"epoch\":").Append(epoch.ToString(CultureInfo.InvariantCulture))
                .Append(",\"stream_base\":").Append(ToLong(sequence["stream_base"]).ToString(CultureInfo.InvariantCulture))
                .Append(",\"high_water\":").Append((ToLong(sequence["next_sequence"]) - 1).ToString(CultureInfo.InvariantCulture))
                .Append(",\"dropped\":[");
            var first = true;
            foreach (List<object> range in (List<object>)sequence["dropped"])
            {
                if (!first) body.Append(',');
                first = false;
                body.Append('[').Append(ToLong(range[0]).ToString(CultureInfo.InvariantCulture)).Append(',').Append(ToLong(range[1]).ToString(CultureInfo.InvariantCulture)).Append(']');
            }
            body.Append("]}");

            var response = _http.PostJson("/v2/streams/sync", body.ToString(), state.InstallationCredential);
            if (response.Status == 401) { early = V7SendResult.Unauthorized(); return false; }
            if (IsTransient(response.Status)) { early = V7SendResult.Retry(response.Status, response.RetryAfter, "sync: " + response.Status); return false; }
            if (response.Status == 409 && response.ErrorCode == "stream_rollback")
            {
                queue.BeginNewStream();               // the server saw a higher sequence than this client has: continue under a new epoch
                _forceSync = true;
                return false;
            }
            if (response.Status == 404 && response.ErrorCode == "unknown_stream")
            {
                queue.BeginNewStream();
                _forceSync = true;
                return false;
            }
            if (!response.IsSuccess)
            {
                // Not found, method not allowed, stream conflict...: this server or project does not do V7 for us right now.
                MarkUnavailable("sync answered " + response.Status + " " + response.ErrorCode);
                early = Fallback(LastFallbackReason);
                return false;
            }

            var result = MiniJson.ParseObject(response.Text);
            var newEpoch = ToLong(result["epoch"]);
            if (newEpoch < 1) throw new FormatException("sync returned an invalid epoch");
            if (newEpoch != epoch) queue.SetStreamEpoch(newEpoch);
            if (newEpoch != _streamEpoch) { _streamEpoch = newEpoch; _aliasesUploaded = 0; }   // the alias table belongs to the stream
            var ack = ToLong(result["ack_through"]);
            if (ack > 0) queue.DeleteThroughSequence(ack);
            _syncedDroppedVersion = droppedVersion;
            _forceSync = false;

            var assets = (Dictionary<string, object>)result["assets"];
            _serverCatalogId = (string)assets["catalog_id"];
            _serverDictionaryId = (string)assets["dictionary_id"];
            if (string.IsNullOrEmpty(_serverCatalogId)) { MarkUnavailable("the project has no V7 catalog"); early = Fallback(LastFallbackReason); return false; }
            if (_encoder != null && (_serverCatalogId != _loadedCatalogId || _serverDictionaryId != _loadedDictionaryId))
            {
                _encoder.Dispose();                   // the project published new assets
                _encoder = null;
            }
            return true;
        }

        private V7SendResult LoadAssetsAndEncoder(AnalyticsQueueState state)
        {
            var catalogResult = Asset(state, "catalog", _serverCatalogId, out var catalogBytes);
            if (catalogResult != null) return catalogResult;
            byte[] dictionaryBytes = null;
            if (!string.IsNullOrEmpty(_serverDictionaryId))
            {
                var dictionaryResult = Asset(state, "dictionary", _serverDictionaryId, out dictionaryBytes);
                if (dictionaryResult != null) return dictionaryResult;
            }
            M7Catalog catalog;
            try { catalog = M7Catalog.Parse(catalogBytes); }
            catch (FormatException error)
            {
                _store.Delete("catalog", _serverCatalogId);
                MarkUnavailable("the project's catalog is unusable: " + error.Message);
                return Fallback(LastFallbackReason);
            }
            if (catalog.Project != _settings.ProjectId)
            {
                MarkUnavailable("the catalog belongs to another project");
                return Fallback(LastFallbackReason);
            }
            // A fresh alias table (and epoch) for every encoder: the server replaces its table when a new alias epoch starts at 0.
            _aliases = new M7Aliases();
            _aliasesUploaded = 0;
            _encoder = new M7EventEncoder(catalog, _aliases, dictionaryBytes, state.InstallationId, _settings.CompressorFactory(dictionaryBytes), _settings.IntegerModel, _settings.StringModel);
            _loadedCatalogId = _serverCatalogId;
            _loadedDictionaryId = _serverDictionaryId;
            return null;
        }

        private V7SendResult Asset(AnalyticsQueueState state, string kind, string id, out byte[] data)
        {
            data = _store.TryRead(kind, id);
            if (data != null && AssetId(data) == id) return null;
            var response = _http.Get("/v2/assets/" + kind + "/" + id + "?project_id=" + Uri.EscapeDataString(_settings.ProjectId) + "&install_id=" + Uri.EscapeDataString(state.InstallationId), state.InstallationCredential);
            if (response.Status == 401) return V7SendResult.Unauthorized();
            if (IsTransient(response.Status)) return V7SendResult.Retry(response.Status, response.RetryAfter, "asset fetch: " + response.Status);
            if (!response.IsSuccess || AssetId(response.Body) != id)
            {
                MarkUnavailable("asset " + kind + " " + id + " could not be fetched or does not match its id (" + response.Status + ")");
                return Fallback(LastFallbackReason);
            }
            data = response.Body;
            _store.Write(kind, id, data);
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

        // --- aliases ----------------------------------------------------------------------------------------

        /// <summary>Uploads alias records the server does not hold yet. Returns a result when the send must stop; sets <paramref name="restart"/> to run the attempt again.</summary>
        private V7SendResult UploadAliases(AnalyticsQueueState state, out bool restart)
        {
            restart = false;
            for (var guard = 0; _aliasesUploaded < _aliases.Count; guard++)
            {
                if (guard > 20) return Fallback("the alias upload does not converge");
                var count = Math.Min(AliasChunk, _aliases.Count - _aliasesUploaded);
                var body = "{\"schema_version\":2,\"project_id\":" + MiniJson.Escape(_settings.ProjectId) + ",\"install_id\":" + MiniJson.Escape(state.InstallationId) +
                           ",\"epoch\":" + _streamEpoch.ToString(CultureInfo.InvariantCulture) + ",\"alias_epoch\":\"" + _aliases.EpochHex + "\",\"start\":" +
                           _aliasesUploaded.ToString(CultureInfo.InvariantCulture) + ",\"records\":" + _aliases.RecordsJson(_aliasesUploaded, count) + "}";
                var response = _http.PutJson("/v2/streams/aliases", body, state.InstallationCredential);
                if (response.Status == 401) return V7SendResult.Unauthorized();
                if (IsTransient(response.Status)) return V7SendResult.Retry(response.Status, response.RetryAfter, "aliases: " + response.Status);
                if (response.IsSuccess) { _aliasesUploaded += count; continue; }
                if (response.Status == 404) { _forceSync = true; restart = true; return null; }
                if (response.Status == 409 && response.ErrorCode == "alias_gap")
                {
                    var held = ParseHeldCount(response.Text);
                    _aliasesUploaded = held >= 0 && held < _aliasesUploaded ? held : 0;
                    continue;
                }
                if (response.Status == 409 && response.ErrorCode == "alias_epoch_mismatch") { _aliasesUploaded = 0; continue; }
                // alias_conflict or anything unexpected: discard this alias table, encoder included, and start over.
                _encoder.Dispose();
                _encoder = null;
                _loadedCatalogId = _loadedDictionaryId = "";
                restart = true;
                if (++_consecutiveFailures >= DisableAfterFailures) { _disabled = true; return Fallback("alias upload failed repeatedly: " + response.Status + " " + response.ErrorCode); }
                return null;
            }
            return null;
        }

        /// <summary>Reads N from the server's alias_gap message ("server holds N records; resend from there").</summary>
        private static int ParseHeldCount(string body)
        {
            try
            {
                var message = (MiniJson.Parse(body) as Dictionary<string, object>)?["message"] as string;
                const string marker = "holds ";
                var start = message.IndexOf(marker, StringComparison.Ordinal);
                if (start < 0) return -1;
                start += marker.Length;
                var end = start;
                while (end < message.Length && char.IsDigit(message[end])) end++;
                return int.Parse(message.Substring(start, end - start), CultureInfo.InvariantCulture);
            }
            catch (Exception) { return -1; }
        }

        // --- packets ------------------------------------------------------------------------------------------

        private V7Response PostPacket(AnalyticsQueueState state, M7EncodeResult encoded)
        {
            var headers = new Dictionary<string, string>
            {
                ["X-Mortris-Project"] = _settings.ProjectId,
                ["X-Mortris-Install"] = state.InstallationId,
                ["X-Mortris-Epoch"] = _streamEpoch.ToString(CultureInfo.InvariantCulture),
                ["X-Mortris-Sent-At"] = _settings.Clock().UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture),
                ["X-Mortris-Sdk"] = _settings.SdkName + "/" + _settings.SdkVersion,
            };
            return _http.PostPacket("/v2/events/packet", encoded.Frame, headers, state.InstallationCredential);
        }

        /// <summary>Maps the packet response. <paramref name="again"/> asks the caller to run the whole attempt once more.</summary>
        private V7SendResult Interpret(IAnalyticsQueueBridge queue, V7Response response, out bool again)
        {
            again = false;
            if (response.Status == 401) return V7SendResult.Unauthorized();
            if (response.Status == 413) return new V7SendResult { Kind = V7ResultKind.PayloadTooLarge, Status = 413 };
            if (IsTransient(response.Status)) return V7SendResult.Retry(response.Status, response.RetryAfter, "packet: " + response.Status);
            if (response.Status == 404 && response.ErrorCode == "unknown_stream") { queue.BeginNewStream(); _forceSync = true; again = true; return null; }
            if (response.Status == 409 && response.ErrorCode == "alias_epoch_mismatch") { _aliasesUploaded = 0; again = true; return null; }
            if (response.Status == 409 && response.ErrorCode == "transport_assets_unknown")
            {
                _store.Delete("catalog", _loadedCatalogId);
                _store.Delete("dictionary", _loadedDictionaryId);
                _encoder?.Dispose();
                _encoder = null;
                _loadedCatalogId = _loadedDictionaryId = "";
                _forceSync = true;
                again = true;
                return null;
            }
            if (!response.IsSuccess)
            {
                if (++_consecutiveFailures >= DisableAfterFailures) _disabled = true;
                return Fallback("packet answered " + response.Status + " " + response.ErrorCode);
            }

            var result = MiniJson.ParseObject(response.Text);
            var ack = ToLong(result["ack_through"]);
            var policy = (Dictionary<string, object>)result["client_policy"];
            var mode = (string)policy["mode"];
            if (mode != "active" && mode != "pause_upload" && mode != "disable_collection") throw new FormatException("unknown client policy mode");
            var removed = queue.DeleteThroughSequence(ack);
            if (removed == 0)
            {
                // The server settled nothing we hold: an earlier number is still open. Never loop on the same batch; after a few
                // rounds give V7 a rest and let V1 deliver (V1 acknowledgements are reported to the server as dropped ranges).
                if (++_noProgress >= MaxNoProgress)
                {
                    _noProgress = 0;
                    MarkUnavailable("V7 acknowledged through " + ack + " without settling any queued event");
                    return Fallback(LastFallbackReason);
                }
                return V7SendResult.Retry(200, null, "packet acknowledged through " + ack + " but removed no queued event");
            }
            _noProgress = 0;
            return new V7SendResult
            {
                Kind = V7ResultKind.Delivered, Removed = removed, PolicyMode = mode, DiscardPending = policy["discard_pending"] is bool discard && discard,
                NextCheckSeconds = (int)ToLong(policy["next_check_seconds"]),
            };
        }

        // --- helpers ------------------------------------------------------------------------------------------

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
