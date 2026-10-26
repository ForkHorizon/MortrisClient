using System;
using System.Collections.Generic;
using System.Security.Cryptography;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>What the frame header says about the stream at the moment of sending.</summary>
    internal struct M8StreamInfo
    {
        internal long Epoch, SentAtMs, StreamBase, HighWater;
        /// <summary>Shapes and alias records the server is known to hold: the frame carries the sections for everything after them.</summary>
        internal int ServerShapes, ServerAliases;
        /// <summary>Sequence ranges dropped locally that the server has not been told about (empty when none).</summary>
        internal IReadOnlyList<KeyValuePair<long, long>> Dropped;
    }

    /// <summary>
    /// Turns a queue batch into one M8 frame (docs/v8-transport.md section 3.1): the V7 column body behind a header that carries the epoch, the send time,
    /// the stream bounds and, when the server lacks them, the alias and shape sections. Shapes are learned as events arrive. Single-threaded (the worker).
    /// </summary>
    internal sealed class M8Encoder : IDisposable
    {
        internal const int MaxRows = 500, MaxRaw = 2097152, MaxFrame = 262144, MaxShapesPerFrame = 512, MaxAliasesPerFrame = 2048, MaxRanges = 4096;
        private readonly M8Shapes _shapes;
        private readonly M8Aliases _aliases;
        private readonly IM7Compressor _compressor;
        private readonly string _sdk;
        private readonly byte[] _dictionaryId = new byte[8];
        private readonly byte _modelFlags;
        private readonly M7Columns _columns = new M7Columns();
        private readonly EventRecordReader _reader = new EventRecordReader();
        private readonly ParsedEvent _parsed = new ParsedEvent();
        private readonly M7Event _event = new M7Event();
        private readonly List<M7Row> _rowPool = new List<M7Row>();
        private readonly List<KeyValuePair<string, int>> _fields = new List<KeyValuePair<string, int>>();
        private readonly Dictionary<string, int> _sessions = new Dictionary<string, int>(StringComparer.Ordinal);
        private byte[] _raw = new byte[64 * 1024];
        private byte[] _frame = new byte[16 * 1024];

        internal M8Encoder(M8Shapes shapes, M8Aliases aliases, byte[] dictionary, IM7Compressor compressor, string sdk, bool integerModel = true, bool stringModel = true)
        {
            _shapes = shapes ?? throw new ArgumentNullException(nameof(shapes));
            _aliases = aliases ?? throw new ArgumentNullException(nameof(aliases));
            _compressor = compressor ?? throw new ArgumentNullException(nameof(compressor));
            _sdk = sdk ?? throw new ArgumentNullException(nameof(sdk));
            if (dictionary != null && dictionary.Length > MaxRaw) throw new ArgumentException("Dictionary is too large.");
            if (dictionary != null && dictionary.Length > 0)
                using (var sha = SHA256.Create())
                    Buffer.BlockCopy(sha.ComputeHash(dictionary), 0, _dictionaryId, 0, 8);
            _modelFlags = (byte)((integerModel ? 2 : 0) | (stringModel ? 4 : 0));
            _integerModel = integerModel; _stringModel = stringModel;
        }

        private readonly bool _integerModel, _stringModel;

        internal M8Shapes Shapes => _shapes;
        internal M8Aliases Aliases => _aliases;

        internal M7EncodeResult Encode(QueueBatch batch, M8StreamInfo info)
        {
            var count = batch.Count;
            if (count < 1 || count > MaxRows) return Fail("batch size " + count + " is outside 1.." + MaxRows);
            if (info.Epoch < 1 || info.StreamBase < 1 || info.HighWater < info.StreamBase) return Fail("stream bounds are invalid");

            var rows = new M7Row[count];
            var sequences = new long[count];
            var sessions = _sessions; sessions.Clear();
            for (var i = 0; i < count; i++)
            {
                M7Event e;
                try
                {
                    batch.Parse(_reader, i, _parsed);
                    e = _event.Fill(_parsed, batch.Sequence(i), logicalStrings: true, typedNumbers: true);
                }
                catch (FormatException error) { return Fail("event " + i + ": " + error.Message); }
                if (i > 0 && e.Sequence <= sequences[i - 1]) return Fail("sequences are not strictly increasing");
                if (e.Sequence < info.StreamBase || e.Sequence > info.HighWater) return Fail("sequence " + e.Sequence + " is outside the stream " + info.StreamBase + ".." + info.HighWater);

                _fields.Clear();
                foreach (var property in e.Properties) _fields.Add(new KeyValuePair<string, int>(property.Key, property.Value.Type));
                var shape = _shapes.Find(e.Name, _fields);
                if (shape < 0 && (shape = _shapes.Add(e.Name, _fields)) < 0) return Fail("event " + e.Name + " cannot be described as a shape");
                if (!_aliases.TryRegister(e, _sdk, out var alias)) return Fail("alias table is full");
                if (!sessions.TryGetValue(e.SessionId, out var session))
                {
                    session = sessions.Count;
                    if (session >= M7Columns.MaxSessions) return Fail("too many sessions in one batch");
                    sessions.Add(e.SessionId, session);
                }

                while (_rowPool.Count <= i) _rowPool.Add(new M7Row());
                var row = _rowPool[i];
                var values = row.Values != null && row.Values.Length == e.Properties.Count ? row.Values : new M7Cell[e.Properties.Count];
                for (var j = 0; j < values.Length; j++)
                {
                    var v = e.Properties[j].Value;
                    values[j] = new M7Cell { I = v.I, U = v.U, D = v.D, S = v.S };
                }
                row.Sequence = e.Sequence; row.Time = e.TimeMs; row.Elapsed = e.SessionElapsedMs; row.Shape = shape; row.Context = alias; row.Session = session;
                row.Columns = _shapes[shape].Columns; row.Values = values; row.Id = null;
                rows[i] = row;
                sequences[i] = e.Sequence;
            }

            if (_shapes.Count - info.ServerShapes > MaxShapesPerFrame) return Fail("too many unsent shapes");
            if (_aliases.Count - info.ServerAliases > MaxAliasesPerFrame) return Fail("too many unsent aliases");
            if (info.ServerAliases < _aliases.Base) return Fail("the server lacks alias slots this process builds on");

            int rawLength;
            while (true)
            {
                try { rawLength = _columns.Pack(rows, _shapes.ColumnTypes, false, _raw, _integerModel, _stringModel); break; }
                catch (M7CapacityException)
                {
                    if (_raw.Length >= MaxRaw) return Fail("the batch does not fit a packet");
                    _raw = new byte[Math.Min(MaxRaw, _raw.Length * 2)];
                }
                catch (ArgumentException) { return Fail("a value is out of range"); }
                catch (OverflowException) { return Fail("a value is out of range"); }
            }
            var compressed = _compressor.Compress(_raw, rawLength);
            var useCompressed = compressed != null && compressed.Length < rawLength;
            var body = useCompressed ? compressed : _raw;
            var bodyLength = useCompressed ? compressed.Length : rawLength;

            var w = new FrameWriter(_frame);
            w.Byte((byte)'M'); w.Byte((byte)'8');
            var newShapes = _shapes.Count - info.ServerShapes;
            var newAliases = _aliases.Count - info.ServerAliases;
            var hasDropped = info.Dropped != null && info.Dropped.Count > 0;
            if (hasDropped && info.Dropped.Count > MaxRanges) return Fail("too many dropped ranges");
            w.Byte((byte)(_modelFlags | (useCompressed ? 1 : 0) | (newAliases > 0 ? 8 : 0) | (newShapes > 0 ? 16 : 0) | (hasDropped ? 32 : 0)));
            w.Bytes(_dictionaryId, 8);
            w.Var((ulong)info.Epoch); w.Var((ulong)info.SentAtMs); w.Var((ulong)info.StreamBase); w.Var((ulong)info.HighWater);
            w.Var((ulong)_shapes.Count); w.Var((ulong)_aliases.Count);
            if (newAliases > 0)
            {
                w.Var((ulong)info.ServerAliases); w.Var((ulong)newAliases);
                for (var position = info.ServerAliases; position < _aliases.Count; position++)
                {
                    var a = _aliases.At(position);
                    w.Uuid(a.SessionId);
                    w.Text(a.AppVersion); w.Text(a.BuildNumber); w.Text(a.Platform); w.Text(a.OsVersion); w.Text(a.DeviceClass); w.Text(a.Locale); w.Text(a.Sdk);
                    w.Var((ulong)((long)a.TimezoneMinutes << 1 ^ (long)a.TimezoneMinutes >> 63));
                }
            }
            if (newShapes > 0)
            {
                w.Var((ulong)info.ServerShapes); w.Var((ulong)newShapes);
                for (var id = info.ServerShapes; id < _shapes.Count; id++)
                {
                    var s = _shapes[id];
                    w.Text(s.Name); w.Var((ulong)s.Keys.Length);
                    for (var j = 0; j < s.Keys.Length; j++) { w.Text(s.Keys[j]); w.Byte((byte)s.Kinds[j]); }
                }
            }
            if (hasDropped)
            {
                w.Var((ulong)info.Dropped.Count);
                foreach (var range in info.Dropped) { w.Var((ulong)range.Key); w.Var((ulong)range.Value); }
            }
            w.Var((ulong)count); w.Var((ulong)rawLength);
            w.Bytes(body, bodyLength);
            if (w.Length + 4 > MaxFrame) return Fail("the frame exceeds " + MaxFrame + " bytes");
            var crc = M7FrameEncoder.Crc(w.Buffer, w.Length);
            for (var i = 0; i < 4; i++) w.Byte((byte)(crc >> (i * 8)));
            _frame = w.Buffer;
            var frame = new byte[w.Length];
            Buffer.BlockCopy(w.Buffer, 0, frame, 0, w.Length);
            return new M7EncodeResult { Ok = true, Frame = frame, Count = count, Sequences = sequences, ShapeCount = _shapes.Count, AliasCount = _aliases.Count };
        }

        public void Dispose() => _compressor.Dispose();

        private static M7EncodeResult Fail(string reason) => new M7EncodeResult { Failure = reason };

        /// <summary>Appends to a growing buffer (the encoder keeps one and reuses it for every frame).</summary>
        private struct FrameWriter
        {
            private byte[] _buffer;
            private int _length;

            internal FrameWriter(byte[] buffer) { _buffer = buffer; _length = 0; }
            internal byte[] Buffer => _buffer;
            internal int Length => _length;

            private void Ensure(int extra)
            {
                if (_length + extra <= _buffer.Length) return;
                var size = _buffer.Length;
                while (size < _length + extra) size *= 2;
                Array.Resize(ref _buffer, size);
            }

            internal void Byte(byte b) { Ensure(1); _buffer[_length++] = b; }
            internal void Bytes(byte[] source, int count) { Ensure(count); System.Buffer.BlockCopy(source, 0, _buffer, _length, count); _length += count; }

            internal void Var(ulong value)
            {
                Ensure(10);
                while (value >= 128) { _buffer[_length++] = (byte)(value | 128); value >>= 7; }
                _buffer[_length++] = (byte)value;
            }

            internal void Text(string s)
            {
                var bytes = System.Text.Encoding.UTF8.GetByteCount(s);
                Var((ulong)bytes);
                Ensure(bytes);
                _length += System.Text.Encoding.UTF8.GetBytes(s, 0, s.Length, _buffer, _length);
            }

            internal void Uuid(string canonical)
            {
                Ensure(16);
                var nibble = 0; var high = true; var written = 0;
                for (var i = 0; i < canonical.Length && written < 16; i++)
                {
                    var c = canonical[i];
                    if (c == '-') continue;
                    var v = c <= '9' ? c - '0' : c - 'a' + 10;
                    if (high) { nibble = v << 4; high = false; }
                    else { _buffer[_length + written++] = (byte)(nibble | v); high = true; }
                }
                _length += 16;
            }
        }
    }
}
