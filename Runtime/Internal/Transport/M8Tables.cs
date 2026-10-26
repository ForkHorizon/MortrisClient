using System;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>One event shape of the V8 transport: an event name and its typed properties, sorted by key. The position in the table is the shape id.</summary>
    internal sealed class M8Shape
    {
        internal string Name;
        internal string[] Keys;
        internal int[] Kinds;
        /// <summary>For each field its column in the shared column table (one column per distinct key and kind).</summary>
        internal int[] Columns;
    }

    /// <summary>
    /// The client's copy of the project's shape table (docs/v8-transport.md section 3.1). Append-only: a shape the client meets that the table lacks is added
    /// at the end and sent to the server inside the next packet; the server's own table (GET /v3/catalog) can replace the local one.
    /// </summary>
    internal sealed class M8Shapes
    {
        internal const int MaxShapes = 4096, MaxFields = 64;
        private readonly List<M8Shape> _shapes = new List<M8Shape>();
        private readonly Dictionary<string, List<int>> _byName = new Dictionary<string, List<int>>(StringComparer.Ordinal);
        private readonly Dictionary<string, int> _columnIndex = new Dictionary<string, int>(StringComparer.Ordinal);
        private readonly List<int> _columnTypes = new List<int>();
        private int[] _columnTypesArray = new int[0];

        internal int Count => _shapes.Count;
        internal M8Shape this[int id] => _shapes[id];

        /// <summary>Type of each column; a row field refers to its column by index. The array is replaced when the table grows.</summary>
        internal int[] ColumnTypes
        {
            get
            {
                if (_columnTypesArray.Length != _columnTypes.Count) _columnTypesArray = _columnTypes.ToArray();
                return _columnTypesArray;
            }
        }

        internal static bool ValidName(string s)
        {
            if (string.IsNullOrEmpty(s) || s.Length > 64 || s[0] < 'a' || s[0] > 'z' || s[s.Length - 1] == '_') return false;
            for (var i = 0; i < s.Length; i++)
            {
                var c = s[i];
                if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) continue;
                if (c != '_' || s[i - 1] == '_') return false;
            }
            return true;
        }

        internal static bool ValidKind(int kind) => kind >= 0 && kind <= 11 && kind != 8 && kind != 9;

        /// <summary>Shape id for an event name and its key-sorted typed fields, or -1.</summary>
        internal int Find(string name, IReadOnlyList<KeyValuePair<string, int>> sortedFields)
        {
            if (!_byName.TryGetValue(name, out var candidates)) return -1;
            for (var c = 0; c < candidates.Count; c++)
            {
                var shape = _shapes[candidates[c]];
                if (shape.Keys.Length != sortedFields.Count) continue;
                var same = true;
                for (var i = 0; same && i < shape.Keys.Length; i++)
                    same = shape.Kinds[i] == sortedFields[i].Value && string.Equals(shape.Keys[i], sortedFields[i].Key, StringComparison.Ordinal);
                if (same) return candidates[c];
            }
            return -1;
        }

        /// <summary>Appends a shape. Returns its id, or -1 when it is not acceptable (invalid name or key, unsorted keys, too many fields, table full).</summary>
        internal int Add(string name, IReadOnlyList<KeyValuePair<string, int>> sortedFields)
        {
            if (_shapes.Count >= MaxShapes || !ValidName(name) || sortedFields.Count > MaxFields) return -1;
            var shape = new M8Shape { Name = name, Keys = new string[sortedFields.Count], Kinds = new int[sortedFields.Count], Columns = new int[sortedFields.Count] };
            for (var i = 0; i < sortedFields.Count; i++)
            {
                var key = sortedFields[i].Key; var kind = sortedFields[i].Value;
                if (!ValidName(key) || !ValidKind(kind) || (i > 0 && string.CompareOrdinal(shape.Keys[i - 1], key) >= 0)) return -1;
                shape.Keys[i] = key; shape.Kinds[i] = kind;
                var columnKey = key + "\u0001" + kind.ToString(CultureInfo.InvariantCulture);
                if (!_columnIndex.TryGetValue(columnKey, out var column))
                {
                    column = _columnTypes.Count;
                    _columnIndex.Add(columnKey, column);
                    _columnTypes.Add(kind);
                }
                shape.Columns[i] = column;
            }
            var id = _shapes.Count;
            _shapes.Add(shape);
            if (!_byName.TryGetValue(name, out var list)) _byName.Add(name, list = new List<int>(1));
            list.Add(id);
            return id;
        }

        /// <summary>Drops the shapes after the first <paramref name="count"/> (those the server never accepted).</summary>
        internal void TruncateTo(int count)
        {
            if (count >= _shapes.Count) return;
            var keep = _shapes.GetRange(0, Math.Max(0, count));
            Clear();
            foreach (var shape in keep)
            {
                var fields = new List<KeyValuePair<string, int>>(shape.Keys.Length);
                for (var i = 0; i < shape.Keys.Length; i++) fields.Add(new KeyValuePair<string, int>(shape.Keys[i], shape.Kinds[i]));
                Add(shape.Name, fields);
            }
        }

        internal void Clear()
        {
            _shapes.Clear(); _byName.Clear(); _columnIndex.Clear(); _columnTypes.Clear(); _columnTypesArray = new int[0];
        }

        /// <summary>The catalog document of GET /v3/catalog (or of the local persisted copy): {"project_id", "shapes":[[name,[[key,kind]...]]...]}.</summary>
        internal string ToJson(string project) => ToJson(project, _shapes.Count);

        /// <summary>The catalog document of the first <paramref name="count"/> shapes.</summary>
        internal string ToJson(string project, int count)
        {
            var json = new StringBuilder("{\"project_id\":").Append(MiniJson.Escape(project)).Append(",\"shapes\":[");
            for (var i = 0; i < count; i++)
            {
                var s = _shapes[i];
                if (i > 0) json.Append(',');
                json.Append('[').Append(MiniJson.Escape(s.Name)).Append(",[");
                for (var j = 0; j < s.Keys.Length; j++)
                {
                    if (j > 0) json.Append(',');
                    json.Append('[').Append(MiniJson.Escape(s.Keys[j])).Append(',').Append(s.Kinds[j].ToString(CultureInfo.InvariantCulture)).Append(']');
                }
                json.Append("]]");
            }
            return json.Append("]}").ToString();
        }

        /// <summary>Replaces the table with the one in the document. Returns false (leaving the table empty) when the document is not a valid shape table.</summary>
        internal bool TryLoad(string json, string project)
        {
            Clear();
            try
            {
                var root = MiniJson.ParseObject(json);
                if (!(root.TryGetValue("project_id", out var p) && p is string pid && pid == project)) return false;
                if (!(root.TryGetValue("shapes", out var s) && s is List<object> shapes) || shapes.Count > MaxShapes) return false;
                foreach (var item in shapes)
                {
                    var tuple = item as List<object>;
                    if (tuple == null || tuple.Count != 2 || !(tuple[0] is string name) || !(tuple[1] is List<object> fields)) { Clear(); return false; }
                    var sorted = new List<KeyValuePair<string, int>>(fields.Count);
                    foreach (var f in fields)
                    {
                        var pair = f as List<object>;
                        if (pair == null || pair.Count != 2 || !(pair[0] is string key) || !(pair[1] is JsonNumber kind) || !int.TryParse(kind.Lexeme, NumberStyles.None, CultureInfo.InvariantCulture, out var k)) { Clear(); return false; }
                        sorted.Add(new KeyValuePair<string, int>(key, k));
                    }
                    if (Add(name, sorted) < 0) { Clear(); return false; }
                }
                return true;
            }
            catch (FormatException) { Clear(); return false; }
        }

        /// <summary>The first 8 bytes of the SHA-256 of the catalog document, in hex: the id the server reports as <c>catalog</c>.</summary>
        internal string CatalogId(string project) => CatalogId(project, _shapes.Count);

        internal string CatalogId(string project, int count)
        {
            // the server hashes the document it generates (encoding/json, compact); ours is generated the same way, but the id is only an equality check
            using (var sha = SHA256.Create())
            {
                var hash = sha.ComputeHash(new UTF8Encoding(false).GetBytes(ToJson(project, count)));
                var builder = new StringBuilder(16);
                for (var i = 0; i < 8; i++) builder.Append(hash[i].ToString("x2", CultureInfo.InvariantCulture));
                return builder.ToString();
            }
        }
    }

    /// <summary>One context record of a stream: the repeated part of every event (see docs/v8-transport.md section 3.1).</summary>
    internal struct M8AliasRecord
    {
        internal string SessionId, AppVersion, BuildNumber, Platform, OsVersion, DeviceClass, Locale, Sdk;
        internal int TimezoneMinutes;
    }

    /// <summary>
    /// The stream's alias table as this process sees it. <see cref="Base"/> slots belong to earlier processes (the server holds them); this process appends after
    /// them and only ever refers to its own records.
    /// </summary>
    internal sealed class M8Aliases
    {
        internal const int MaxRecords = 65536;
        private readonly List<M8AliasRecord> _records = new List<M8AliasRecord>();
        private readonly Dictionary<string, int> _index = new Dictionary<string, int>(StringComparer.Ordinal);
        private M7Event _last;
        private int _lastIndex;

        internal int Base { get; private set; }
        internal int Count => Base + _records.Count;

        /// <summary>Starts a table whose first <paramref name="serverCount"/> slots are held by the server from before.</summary>
        internal void Reset(int serverCount)
        {
            _records.Clear(); _index.Clear(); _last = null;
            Base = serverCount;
        }

        internal M8AliasRecord At(int position) => _records[position - Base];

        internal bool TryRegister(M7Event e, string sdk, out int index)
        {
            var last = _last;
            if (last != null && ReferenceEquals(last.SessionId, e.SessionId) && ReferenceEquals(last.AppVersion, e.AppVersion) && ReferenceEquals(last.BuildNumber, e.BuildNumber) &&
                ReferenceEquals(last.Platform, e.Platform) && ReferenceEquals(last.OsVersion, e.OsVersion) && ReferenceEquals(last.DeviceClass, e.DeviceClass) &&
                ReferenceEquals(last.Locale, e.Locale) && last.TimezoneOffsetMinutes == e.TimezoneOffsetMinutes)
            {
                index = _lastIndex;
                return true;
            }
            var key = string.Join("\u0001", e.SessionId, e.AppVersion, e.BuildNumber, e.Platform, e.OsVersion, e.DeviceClass, e.Locale, e.TimezoneOffsetMinutes.ToString(CultureInfo.InvariantCulture));
            if (!_index.TryGetValue(key, out var local))
            {
                if (Count >= MaxRecords) { index = -1; return false; }
                local = _records.Count;
                _index.Add(key, local);
                _records.Add(new M8AliasRecord
                {
                    SessionId = e.SessionId, AppVersion = e.AppVersion, BuildNumber = e.BuildNumber, Platform = e.Platform, OsVersion = e.OsVersion,
                    DeviceClass = e.DeviceClass, Locale = e.Locale, Sdk = sdk, TimezoneMinutes = e.TimezoneOffsetMinutes,
                });
            }
            index = Base + local;
            (_last ?? (_last = new M7Event())).CopyContextFrom(e);
            _lastIndex = index;
            return true;
        }
    }
}
