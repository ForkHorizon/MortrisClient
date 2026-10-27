using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using Daliys.Analytics.Internal.Transport;
using Xunit;
using Xunit.Abstractions;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>
    /// PROTOTYPE (tests only, not in the shipped protocol): the V8 presence mask. The shipped format describes a row by a shape id (the exact set of typed keys of one event name); the
    /// prototype describes it by the event-name id plus a bitmask over that name's typed columns, with a "same mask as this name's previous row" flag. The value columns are the
    /// same. <see cref="PackBucketed"/> is the shipped format with an O(rows x fields) value gather instead of O(columns x rows x fields): same bytes, checked by a test.
    /// </summary>
    internal sealed partial class M7Columns
    {
        private void PrepareHeader(M7Row[] rows, bool numeric, bool stringsModel, byte[] destination)
        {
            if (rows.Length < 1 || rows.Length > 500) throw new ArgumentException("bounds");
            integerModel = numeric; stringModel = stringsModel; output = destination; pos = 0; Array.Clear(seen, 0, seen.Length); Array.Clear(previousSeen, 0, previousSeen.Length);
        }

        private void StructuralColumns(M7Row[] rows)
        {
            for (var col = 0; col < 5; col++)
            {
                for (var i = 0; i < rows.Length; i++)
                {
                    var r = rows[i];
                    var value = col == 0 ? r.Sequence : col == 1 ? r.Time : col == 2 ? r.Elapsed : col == 3 ? r.Shape : r.Context;
                    if (col == 2)
                    {
                        if (previousSeen[r.Session]) value = checked(r.Elapsed - previousElapsed[r.Session] - r.Time + previousTime[r.Session]);
                        previousSeen[r.Session] = true; previousElapsed[r.Session] = r.Elapsed; previousTime[r.Session] = r.Time;
                    }
                    work[i] = value;
                }
                Ints(rows.Length);
            }
        }

        /// <summary>The shipped format (shape id column), faster gather.</summary>
        internal int PackBucketed(M7Row[] rows, int[] types, byte[] destination, bool numeric = false, bool stringsModel = false)
        {
            PrepareHeader(rows, numeric, stringsModel, destination);
            StructuralColumns(rows);
            ValueColumnsBucketed(rows, types);
            return pos;
        }

        /// <summary>
        /// The mask format: column 3 holds the event-name id; then a flag per row (1 = this row's mask differs from the previous row of the same name), then the masks of the flagged rows.
        /// <paramref name="masks"/> holds each row's presence mask over its name's columns (at most 64 per name in the prototype).
        /// </summary>
        internal int PackMasked(M7Row[] rows, ulong[] masks, bool[] explicitMask, int[] types, byte[] destination, bool numeric = false, bool stringsModel = false)
        {
            PrepareHeader(rows, numeric, stringsModel, destination);
            StructuralColumns(rows);
            for (var i = 0; i < rows.Length; i++) work[i] = explicitMask[i] ? 1 : 0;
            Ints(rows.Length);
            var k = 0;
            for (var i = 0; i < rows.Length; i++) if (explicitMask[i]) work[k++] = unchecked((long)masks[i]);
            if (k > 0) Ints(k);
            ValueColumnsBucketed(rows, types);
            return pos;
        }
    }
}

namespace M7Transport.Tests
{
    /// <summary>Encoder-side prototype of the presence mask next to the shipped shape rows; both use the same value-column coder.</summary>
    internal sealed class MaskPrototypeEncoder : IDisposable
    {
        private sealed class NameEntry
        {
            internal int Id;
            internal readonly List<int> Columns = new List<int>();
            internal readonly Dictionary<int, int> BitOf = new Dictionary<int, int>();
            internal ulong LastMask;
            internal bool HasLast;
        }

        internal readonly M8Shapes Shapes = new M8Shapes();
        internal readonly List<int> ColumnTypes = new List<int>();
        private readonly Dictionary<string, int> _columnOf = new Dictionary<string, int>(StringComparer.Ordinal);
        private readonly Dictionary<string, NameEntry> _names = new Dictionary<string, NameEntry>(StringComparer.Ordinal);
        private readonly EventRecordReader _reader = new EventRecordReader();
        private readonly ParsedEvent _parsed = new ParsedEvent();
        private readonly M7Event _event = new M7Event();
        private readonly M7Columns _columns = new M7Columns();
        private readonly List<KeyValuePair<string, int>> _fields = new List<KeyValuePair<string, int>>();
        private readonly Dictionary<string, int> _sessions = new Dictionary<string, int>(StringComparer.Ordinal);
        private readonly List<M7Row> _pool = new List<M7Row>();
        private readonly byte[] _raw = new byte[512 * 1024];
        private readonly NativeZstdCompressor _zstd = new NativeZstdCompressor(null);
        private int[] _columnTypesArray = new int[0];

        internal int NameCount => _names.Count;

        internal sealed class Packed
        {
            internal int RawLength, CompressedLength, Events, Explicit;
            internal M7Row[] Rows; internal ulong[] Masks; internal bool[] ExplicitMask; internal int[] NameIds; internal List<List<KeyValuePair<string, int>>> Fields;
        }

        private int[] MaskColumnTypes()
        {
            if (_columnTypesArray.Length != ColumnTypes.Count) _columnTypesArray = ColumnTypes.ToArray();
            return _columnTypesArray;
        }

        /// <summary>Builds the rows of a batch for either design (the cost of this step is part of what is compared).</summary>
        internal Packed Build(QueueBatch batch, bool mask)
        {
            var count = batch.Count; var rows = new M7Row[count]; var masks = new ulong[count]; var flags = new bool[count]; var nameIds = new int[count];
            var fieldsPerRow = new List<List<KeyValuePair<string, int>>>(count); var explicitCount = 0;
            _sessions.Clear();
            for (var i = 0; i < count; i++)
            {
                batch.Parse(_reader, i, _parsed);
                var e = _event.Fill(_parsed, batch.Sequence(i), logicalStrings: true, typedNumbers: true);
                _fields.Clear();
                foreach (var property in e.Properties) _fields.Add(new KeyValuePair<string, int>(property.Key, property.Value.Type));
                while (_pool.Count <= i) _pool.Add(new M7Row());
                var row = _pool[i]; rows[i] = row;
                if (!_sessions.TryGetValue(e.SessionId, out var session)) { session = _sessions.Count; _sessions.Add(e.SessionId, session); }
                var values = new M7Cell[e.Properties.Count];
                for (var j = 0; j < values.Length; j++) { var v = e.Properties[j].Value; values[j] = new M7Cell { I = v.I, U = v.U, D = v.D, S = v.S }; }
                row.Sequence = e.Sequence; row.Time = e.TimeMs; row.Elapsed = e.SessionElapsedMs; row.Context = 0; row.Session = session; row.Values = values; row.Id = null;
                if (!mask)
                {
                    var shape = Shapes.Find(e.Name, _fields);
                    if (shape < 0) shape = Shapes.Add(e.Name, _fields);
                    row.Shape = shape; row.Columns = Shapes[shape].Columns;
                }
                else
                {
                    if (!_names.TryGetValue(e.Name, out var entry)) { entry = new NameEntry { Id = _names.Count }; _names.Add(e.Name, entry); }
                    var columns = new int[_fields.Count]; ulong m = 0;
                    for (var j = 0; j < _fields.Count; j++)
                    {
                        var key = _fields[j].Key + "\u0001" + _fields[j].Value;
                        if (!_columnOf.TryGetValue(key, out var column)) { column = ColumnTypes.Count; _columnOf.Add(key, column); ColumnTypes.Add(_fields[j].Value); }
                        if (!entry.BitOf.TryGetValue(column, out var bit))
                        {
                            bit = entry.Columns.Count;
                            if (bit >= 64) throw new NotSupportedException("the prototype keeps at most 64 columns per event name");
                            entry.BitOf.Add(column, bit); entry.Columns.Add(column);
                        }
                        columns[j] = column; m |= 1UL << bit;
                    }
                    row.Shape = entry.Id; row.Columns = columns; masks[i] = m; nameIds[i] = entry.Id;
                    if (!entry.HasLast || entry.LastMask != m) { flags[i] = true; entry.LastMask = m; entry.HasLast = true; explicitCount++; }
                }
                fieldsPerRow.Add(new List<KeyValuePair<string, int>>(_fields));
            }
            return new Packed { Rows = rows, Masks = masks, ExplicitMask = flags, NameIds = nameIds, Fields = fieldsPerRow, Events = count, Explicit = explicitCount };
        }

        internal Packed Pack(QueueBatch batch, bool mask, bool bucketedShape = true)
        {
            var packed = Build(batch, mask);
            packed.RawLength = mask ? _columns.PackMasked(packed.Rows, packed.Masks, packed.ExplicitMask, MaskColumnTypes(), _raw, true, true)
                : bucketedShape ? _columns.PackBucketed(packed.Rows, Shapes.ColumnTypes, _raw, true, true) : _columns.Pack(packed.Rows, Shapes.ColumnTypes, false, _raw, true, true);
            var compressed = _zstd.Compress(_raw, packed.RawLength);
            packed.CompressedLength = compressed != null && compressed.Length < packed.RawLength ? compressed.Length : packed.RawLength;
            return packed;
        }

        /// <summary>Packs already-built shape rows with the shipped column coder (for the byte-equality check against <see cref="M7Columns.PackBucketed"/>).</summary>
        internal byte[] PackShipped(Packed built, bool bucketed)
        {
            var length = bucketed ? _columns.PackBucketed(built.Rows, Shapes.ColumnTypes, _raw, true, true) : _columns.Pack(built.Rows, Shapes.ColumnTypes, false, _raw, true, true);
            return _raw.Take(length).ToArray();
        }

        /// <summary>The model check of the mask format: from the name catalog and the masks alone, every row's typed key set must be recovered exactly (null stays a kind, absent stays absent).</summary>
        internal void VerifyMasksRecoverTheRows(Packed packed)
        {
            var nameOf = new Dictionary<int, NameEntry>(); foreach (var kv in _names) nameOf[kv.Value.Id] = kv.Value;
            var keyOf = new Dictionary<int, string>(); foreach (var kv in _columnOf) keyOf[kv.Value] = kv.Key;
            for (var i = 0; i < packed.Events; i++)
            {
                var entry = nameOf[packed.NameIds[i]]; var recovered = new List<string>();
                for (var bit = 0; bit < entry.Columns.Count; bit++) if (((packed.Masks[i] >> bit) & 1) != 0) recovered.Add(keyOf[entry.Columns[bit]]);
                var original = packed.Fields[i].Select(f => f.Key + "\u0001" + f.Value).ToList();
                Assert.Equal(original.OrderBy(x => x, StringComparer.Ordinal).ToList(), recovered.OrderBy(x => x, StringComparer.Ordinal).ToList());
            }
        }

        public void Dispose() => _zstd.Dispose();
    }

    public class MaskPrototypeTests
    {
        private readonly ITestOutputHelper _out;
        public MaskPrototypeTests(ITestOutputHelper output) { _out = output; }
        private static readonly byte[] Context = EventContext.Build("1.1.14", "214", "android", "Android 15", "Pixel 8", "en-US", 60);

        private static (FakeQueue queue, int count) Fill(string file, int limit)
        {
            var writer = new EventRecordWriter { TypedNumbers = true }; var frames = new List<byte>(); var n = 0;
            foreach (var line in File.ReadLines(file))
            {
                if (n >= limit) break;
                using (var doc = System.Text.Json.JsonDocument.Parse(line))
                {
                    var props = new Dictionary<string, object>();
                    foreach (var kv in doc.RootElement.GetProperty("props").EnumerateObject())
                        props[kv.Name] = kv.Value.ValueKind == System.Text.Json.JsonValueKind.String ? kv.Value.GetString()
                            : kv.Value.ValueKind == System.Text.Json.JsonValueKind.True ? true : kv.Value.ValueKind == System.Text.Json.JsonValueKind.False ? false
                            : kv.Value.ValueKind == System.Text.Json.JsonValueKind.Null ? null
                            : kv.Value.TryGetInt64(out var l) ? (object)l : kv.Value.GetDouble();
                    if (props.Count > 32) continue;
                    writer.Begin(Guid.NewGuid(), Guid.Parse("7b1f3c52-9a44-4e0e-8d61-2f5c0a9e1b77"), 1790000000000 + n * 40, n * 40 + 10, Context, doc.RootElement.GetProperty("name").GetString(), props.Count);
                    foreach (var p in props) writer.AddClr(p.Key, p.Value);
                    var length = writer.Finish();
                    frames.AddRange(new[] { (byte)(length >> 24), (byte)(length >> 16), (byte)(length >> 8), (byte)length }); frames.AddRange(writer.Buffer.Take(length)); n++;
                }
            }
            var queue = new FakeQueue(); queue.EnqueueRecords(frames.ToArray(), n, 1000000, 1L << 40, 1L << 40);
            return (queue, n);
        }

        /// <summary>A small synthetic corpus with optional keys, a null, and a key that changes type, so the checks do not depend on the data directory.</summary>
        private static string SyntheticCorpus()
        {
            var path = Path.Combine(Path.GetTempPath(), "mask_synthetic.jsonl"); var rng = new Random(11);
            using (var w = new StreamWriter(path))
                for (var i = 0; i < 600; i++)
                {
                    var props = new List<string> { "\"level\":" + (i % 9) };
                    if (rng.Next(2) == 0) props.Add("\"reward\":" + rng.Next(100));
                    if (rng.Next(3) == 0) props.Add("\"note\":\"n" + rng.Next(5) + "\"");
                    if (rng.Next(5) == 0) props.Add("\"target\":null");
                    props.Add(rng.Next(4) == 0 ? "\"score\":" + (rng.NextDouble() * 10).ToString("F3", System.Globalization.CultureInfo.InvariantCulture) : "\"score\":" + rng.Next(1000));
                    w.WriteLine("{\"name\":\"" + (i % 3 == 0 ? "level_end" : i % 3 == 1 ? "item_used" : "tick") + "\",\"props\":{" + string.Join(",", props) + "}}");
                }
            return path;
        }

        [Fact]
        public void TheBucketedGatherWritesExactlyTheBytesOfTheShippedPack()
        {
            var (queue, count) = Fill(SyntheticCorpus(), 600);
            using (var encoder = new MaskPrototypeEncoder())
                for (var from = 0; from + 100 <= count; from += 100)
                {
                    var built = encoder.Build(queue.SliceForTest(from, 100), mask: false);
                    Assert.Equal(encoder.PackShipped(built, bucketed: false), encoder.PackShipped(built, bucketed: true));
                }
        }

        [Fact]
        public void MasksRecoverEveryRowsTypedKeysIncludingNullAndAbsent()
        {
            var (queue, count) = Fill(SyntheticCorpus(), 600);
            using (var encoder = new MaskPrototypeEncoder())
                for (var from = 0; from + 100 <= count; from += 100)
                {
                    var packed = encoder.Pack(queue.SliceForTest(from, 100), mask: true);
                    encoder.VerifyMasksRecoverTheRows(packed);
                    Assert.True(packed.Explicit < 100);                       // the "same as previous" flag saves most masks
                }
        }

        /// <summary>The measurement for the big run: shipped shapes (shipped Pack), shapes with the bucketed gather, and the mask, per corpus and packet size. Does nothing without M8_CORPUS_DIR.</summary>
        [Fact]
        public void MaskVersusShapesOnTheCorpora()
        {
            var dir = Environment.GetEnvironmentVariable("M8_CORPUS_DIR");
            if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) return;
            foreach (var file in Directory.GetFiles(dir, "*_slice_00.jsonl").OrderBy(f => f))
                foreach (var size in new[] { 20, 200, 500 })
                {
                    var (queue, count) = Fill(file, 3000);
                    var slices = new List<QueueBatch>();
                    for (var from = 0; from + size <= count; from += size) slices.Add(queue.SliceForTest(from, size));
                    var n = slices.Count * size;
                    var lines = new List<string>();
                    foreach (var variant in new[] { ("shapes (shipped gather)", false, false), ("shapes (bucketed gather)", false, true), ("mask + same-flag", true, true) })
                    {
                        using (var encoder = new MaskPrototypeEncoder())
                        {
                            foreach (var s in slices) encoder.Pack(s, variant.Item2, variant.Item3);                   // warm-up: shapes / names / columns learned, JIT
                            long raw = 0, zstd = 0; var explicitMasks = 0;
                            GC.Collect(); GC.WaitForPendingFinalizers();
                            var before = GC.GetAllocatedBytesForCurrentThread(); var watch = Stopwatch.StartNew();
                            foreach (var s in slices) { var p = encoder.Pack(s, variant.Item2, variant.Item3); raw += p.RawLength; zstd += p.CompressedLength; explicitMasks += p.Explicit; }
                            watch.Stop();
                            var alloc = (GC.GetAllocatedBytesForCurrentThread() - before) / (double)n;
                            lines.Add(string.Format("    {0,-26} raw {1,7:F2} B/event  zstd {2,7:F2} B/event  {3,7:F2} us/event  {4,7:F0} B alloc/event  shapes {5,4} names {6,3} columns {7,5}",
                                variant.Item1, raw / (double)n, zstd / (double)n, watch.Elapsed.TotalMilliseconds * 1000 / n, alloc, encoder.Shapes.Count, encoder.NameCount, encoder.ColumnTypes.Count));
                        }
                    }
                    _out.WriteLine(Path.GetFileName(file) + " packet " + size + ":"); foreach (var l in lines) _out.WriteLine(l);
                }
        }
    }
}
