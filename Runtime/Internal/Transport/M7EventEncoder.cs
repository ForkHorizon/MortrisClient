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
        private readonly EventRecordReader _reader = new EventRecordReader();
        private readonly ParsedEvent _parsed = new ParsedEvent();
        private M7Event _lastContextEvent;
        private int _lastContextIndex;

        internal M7EventEncoder(M7Catalog catalog, M7Aliases aliases, byte[] dictionary, string origin, IM7Compressor compressor, bool integerModel = true, bool stringModel = true)
        {
            _catalog = catalog ?? throw new ArgumentNullException(nameof(catalog));
            _aliases = aliases ?? throw new ArgumentNullException(nameof(aliases));
            _origin = origin ?? throw new ArgumentNullException(nameof(origin));
            _frames = new M7FrameEncoder(compressor, catalog.Id, aliases.Epoch, dictionary, integerModel, stringModel);
        }

        internal M7Catalog Catalog => _catalog;
        internal M7Aliases Aliases => _aliases;

        /// <summary>Encodes JSON event payloads (the form older SDK versions queued, and the test fixtures): converted to records first.</summary>
        internal M7EncodeResult Encode(string eventsJson)
        {
            QueueBatch batch;
            try { batch = QueueBatch.FromJsonArray(eventsJson); }
            catch (FormatException error) { return Fail("queued batch is not valid: " + error.Message); }
            return Encode(batch);
        }

        internal M7EncodeResult Encode(QueueBatch batch)
        {
            var count = batch.Count;
            if (count < 1 || count > M7FrameEncoder.MaxRows) return Fail("batch size " + count + " is outside 1.." + M7FrameEncoder.MaxRows);

            var rows = new M7Row[count];
            var sequences = new long[count];
            var sessions = new Dictionary<string, int>(StringComparer.Ordinal);
            var fields = new List<KeyValuePair<string, int>>();
            var parsed = _parsed;
            for (var i = 0; i < count; i++)
            {
                M7Event e;
                try
                {
                    batch.Parse(_reader, i, parsed);
                    e = M7Event.FromParsed(parsed, batch.Sequence(i), _catalog.LogicalStrings);
                }
                catch (FormatException error) { return Fail("event " + i + ": " + error.Message); }
                if (i > 0 && e.Sequence <= sequences[i - 1]) return Fail("sequences are not strictly increasing");
                if (e.Sequence < 1) return Fail("sequence must be at least 1");

                fields.Clear();
                foreach (var property in e.Properties) fields.Add(new KeyValuePair<string, int>(property.Key, property.Value.Type));
                var shape = _catalog.FindShape(e.Name, fields);
                if (shape < 0) return Fail("unknown shape for event " + e.Name);
                if (!TryRegister(e, out var context)) return Fail("alias table is full");
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

        /// <summary>Alias index of the event's context; consecutive events of one run share the strings of the record reader, so the previous answer is reused.</summary>
        private bool TryRegister(M7Event e, out int index)
        {
            var last = _lastContextEvent;
            if (last != null && ReferenceEquals(last.SessionId, e.SessionId) && ReferenceEquals(last.AppVersion, e.AppVersion) && ReferenceEquals(last.BuildNumber, e.BuildNumber) &&
                ReferenceEquals(last.Platform, e.Platform) && ReferenceEquals(last.OsVersion, e.OsVersion) && ReferenceEquals(last.DeviceClass, e.DeviceClass) &&
                ReferenceEquals(last.Locale, e.Locale) && last.TimezoneOffsetMinutes == e.TimezoneOffsetMinutes)
            {
                index = _lastContextIndex;
                return true;
            }
            if (!_aliases.TryRegister(_origin, e, out index)) return false;
            _lastContextEvent = e;
            _lastContextIndex = index;
            return true;
        }

        public void Dispose() => _frames.Dispose();

        private static M7EncodeResult Fail(string reason) => new M7EncodeResult { Failure = reason };
    }
}
