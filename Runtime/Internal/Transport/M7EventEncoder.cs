using System;
using System.Collections.Generic;

namespace Daliys.Analytics.Internal.Transport
{
    internal sealed class M7EncodeResult
    {
        internal bool Ok;
        internal byte[] Frame;
        internal int Count;
        /// <summary>Sequences of the events in the frame, in order.</summary>
        internal long[] Sequences;
        /// <summary>Why the batch cannot be sent as V7 (the caller falls back to V1 for it).</summary>
        internal string Failure;
    }

    /// <summary>
    /// Turns a queue batch (JSON array of event payloads) into one M7 packet using the project catalog, the stream's alias table
    /// and the project dictionary. Does no I/O. A batch containing a shape the catalog does not know is not encoded at all.
    /// </summary>
    internal sealed class M7EventEncoder : IDisposable
    {
        private readonly M7Catalog _catalog;
        private readonly M7Aliases _aliases;
        private readonly string _origin;
        private readonly M7FrameEncoder _frames;

        internal M7EventEncoder(M7Catalog catalog, M7Aliases aliases, byte[] dictionary, string origin, IM7Compressor compressor, bool integerModel = true, bool stringModel = true)
        {
            _catalog = catalog ?? throw new ArgumentNullException(nameof(catalog));
            _aliases = aliases ?? throw new ArgumentNullException(nameof(aliases));
            _origin = origin ?? throw new ArgumentNullException(nameof(origin));
            _frames = new M7FrameEncoder(compressor, catalog.Id, aliases.Epoch, dictionary, integerModel, stringModel);
        }

        internal M7Catalog Catalog => _catalog;
        internal M7Aliases Aliases => _aliases;

        internal M7EncodeResult Encode(string eventsJson)
        {
            List<object> raw;
            try { raw = MiniJson.ParseArray(eventsJson); }
            catch (FormatException error) { return Fail("queued batch is not valid JSON: " + error.Message); }
            if (raw.Count < 1 || raw.Count > M7FrameEncoder.MaxRows) return Fail("batch size " + raw.Count + " is outside 1.." + M7FrameEncoder.MaxRows);

            var rows = new M7Row[raw.Count];
            var sequences = new long[raw.Count];
            var sessions = new Dictionary<string, int>(StringComparer.Ordinal);
            var fields = new List<KeyValuePair<string, int>>();
            for (var i = 0; i < raw.Count; i++)
            {
                M7Event e;
                try { e = M7Event.Parse(raw[i] as Dictionary<string, object> ?? throw new FormatException("event is not an object"), _catalog.LogicalStrings); }
                catch (FormatException error) { return Fail("event " + i + ": " + error.Message); }
                if (i > 0 && e.Sequence <= sequences[i - 1]) return Fail("sequences are not strictly increasing");
                if (e.Sequence < 1) return Fail("sequence must be at least 1");

                fields.Clear();
                foreach (var property in e.Properties) fields.Add(new KeyValuePair<string, int>(property.Key, property.Value.Type));
                var shape = _catalog.FindShape(e.Name, fields);
                if (shape < 0) return Fail("unknown shape for event " + e.Name);
                if (!_aliases.TryRegister(_origin, e, out var context)) return Fail("alias table is full");
                if (!sessions.TryGetValue(e.SessionId, out var session))
                {
                    session = sessions.Count;
                    if (session >= M7Columns.MaxSessions) return Fail("too many sessions in one batch");
                    sessions.Add(e.SessionId, session);
                }

                var values = new M7Cell[e.Properties.Count];
                for (var j = 0; j < values.Length; j++)
                {
                    var v = e.Properties[j].Value;
                    values[j] = new M7Cell { I = v.I, U = v.U, D = v.D, S = v.S };
                }
                rows[i] = new M7Row { Sequence = e.Sequence, Time = e.TimeMs, Elapsed = e.SessionElapsedMs, Shape = shape, Context = context, Session = session, Columns = _catalog.ShapeColumns[shape], Values = values };
                sequences[i] = e.Sequence;
            }

            if (!_frames.TryPack(rows, _catalog.ColumnTypes, out var frame)) return Fail("the batch does not fit a packet (value out of range or too large)");
            return new M7EncodeResult { Ok = true, Frame = frame, Count = rows.Length, Sequences = sequences };
        }

        public void Dispose() => _frames.Dispose();

        private static M7EncodeResult Fail(string reason) => new M7EncodeResult { Failure = reason };
    }
}
