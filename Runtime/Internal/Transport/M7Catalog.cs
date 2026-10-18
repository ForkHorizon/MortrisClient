using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>
    /// A project's V7 catalog: the set of event shapes (event name plus typed property keys) the server will decode.
    /// Parsed from the immutable asset the server delivers; identified by the first 8 bytes of its SHA-256.
    /// </summary>
    internal sealed class M7Catalog
    {
        internal const int TypeInt = 0, TypeString = 1, TypeBool = 2, TypeFloat32 = 3, TypeFloat64 = 4, TypeUuid = 5, TypeHex = 6, TypeNull = 7, TypeUInt64 = 10, TypeNumericText = 11;
        private readonly Dictionary<string, int> _shapeBySignature = new Dictionary<string, int>(StringComparer.Ordinal);

        private M7Catalog() { }

        internal string Project { get; private set; }
        internal byte[] Id { get; private set; }
        internal bool LogicalStrings { get; private set; }
        /// <summary>Type of each catalog column (a distinct key and type pair); a row field refers to a column by index.</summary>
        internal int[] ColumnTypes { get; private set; }
        /// <summary>For each shape, its column indices in field (sorted key) order.</summary>
        internal int[][] ShapeColumns { get; private set; }
        internal int ShapeCount => ShapeColumns.Length;

        internal static M7Catalog Parse(byte[] data)
        {
            if (data == null || data.Length == 0 || data.Length > M7FrameEncoder.MaxRaw) throw new FormatException("Catalog size is invalid.");
            var root = MiniJson.ParseObject(new UTF8Encoding(false, true).GetString(data));
            var catalog = new M7Catalog { Project = RequireString(root, "project_id"), LogicalStrings = root.TryGetValue("logical_strings", out var logical) && logical is bool flag && flag };
            using (var sha = SHA256.Create())
            {
                catalog.Id = new byte[8];
                Buffer.BlockCopy(sha.ComputeHash(data), 0, catalog.Id, 0, 8);
            }
            var shapes = root.TryGetValue("shapes", out var shapesValue) && shapesValue is List<object> list ? list : throw new FormatException("Catalog has no shapes.");
            if (shapes.Count > 16000) throw new FormatException("Catalog has too many shapes.");
            var columnIndex = new Dictionary<string, int>(StringComparer.Ordinal);
            var columnTypes = new List<int>();
            catalog.ShapeColumns = new int[shapes.Count][];
            for (var shapeId = 0; shapeId < shapes.Count; shapeId++)
            {
                var tuple = shapes[shapeId] as List<object>;
                if (tuple == null || tuple.Count != 2 || !(tuple[0] is string name) || !(tuple[1] is List<object> fields) || fields.Count > 32)
                    throw new FormatException("Catalog shape is invalid.");
                var columns = new int[fields.Count];
                var signature = new StringBuilder(name);
                string previousKey = null;
                for (var i = 0; i < fields.Count; i++)
                {
                    var pair = fields[i] as List<object>;
                    if (pair == null || pair.Count != 2 || !(pair[0] is string key) || !(pair[1] is JsonNumber number) || !int.TryParse(number.Lexeme, out var type))
                        throw new FormatException("Catalog field is invalid.");
                    if (previousKey != null && string.CompareOrdinal(previousKey, key) >= 0) throw new FormatException("Catalog fields must be sorted by key.");
                    previousKey = key;
                    var columnKey = key + "\u0001" + type;
                    if (!columnIndex.TryGetValue(columnKey, out var column))
                    {
                        column = columnTypes.Count;
                        columnIndex.Add(columnKey, column);
                        columnTypes.Add(type);
                    }
                    columns[i] = column;
                    AppendSignature(signature, key, type);
                }
                catalog.ShapeColumns[shapeId] = columns;
                var finished = signature.ToString();
                if (catalog._shapeBySignature.ContainsKey(finished)) throw new FormatException("Catalog has a duplicate shape.");
                catalog._shapeBySignature.Add(finished, shapeId);
            }
            catalog.ColumnTypes = columnTypes.ToArray();
            return catalog;
        }

        /// <summary>Shape id for an event name and its (key-sorted) typed fields, or -1 when the catalog does not know it.</summary>
        internal int FindShape(string name, IReadOnlyList<KeyValuePair<string, int>> sortedFields)
        {
            var signature = new StringBuilder(name);
            foreach (var field in sortedFields) AppendSignature(signature, field.Key, field.Value);
            return _shapeBySignature.TryGetValue(signature.ToString(), out var id) ? id : -1;
        }

        private static void AppendSignature(StringBuilder signature, string key, int type) =>
            signature.Append('\u0002').Append(key).Append('\u0001').Append(type);

        private static string RequireString(Dictionary<string, object> root, string key) =>
            root.TryGetValue(key, out var value) && value is string text && text.Length > 0 ? text : throw new FormatException("Catalog is missing " + key + ".");
    }
}
