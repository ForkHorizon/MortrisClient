// Rows read from the durable queue: sequence numbers and record bytes, with legacy JSON rows converted to records.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>
    /// Rows read from the queue: for each, its sequence number and record bytes. Wire form from the Java queue:
    /// <c>int32 count</c>, then per row <c>u8 format, int64 sequence, int32 length, bytes</c> (big-endian). Format 0 is a JSON payload written by an
    /// older SDK version and is converted to a record here; format 1 is a record.
    /// </summary>
    internal sealed class QueueBatch
    {
        private readonly byte[][] _buffers;
        private readonly int[] _starts, _ends;
        private readonly long[] _sequences;
        private ParsedEvent _scratch;

        private QueueBatch(int count)
        {
            Count = count;
            _buffers = new byte[count][]; _starts = new int[count]; _ends = new int[count]; _sequences = new long[count];
        }

        internal int Count { get; private set; }
        internal long Sequence(int index) => _sequences[index];
        internal long FirstSequence => Count > 0 ? _sequences[0] : 0;
        internal long LastSequence => Count > 0 ? _sequences[Count - 1] : 0;
        internal string EventId(int index) => EventRecordFormat.UuidText(_buffers[index], _starts[index] + EventRecordFormat.IdOffset);

        internal void Parse(EventRecordReader reader, int index, ParsedEvent into) => reader.Read(_buffers[index], _starts[index], _ends[index], into);

        internal static QueueBatch Empty => new QueueBatch(0);

        internal static QueueBatch FromFrame(byte[] frame)
        {
            if (frame == null || frame.Length < 4) return Empty;
            var position = 0;
            var count = ReadInt32(frame, ref position);
            if (count < 0) throw new FormatException("Queue batch is invalid.");
            var batch = new QueueBatch(count);
            var kept = 0;
            for (var i = 0; i < count; i++)
            {
                if (position + 13 > frame.Length) throw new FormatException("Queue batch is truncated.");
                var format = frame[position++];
                var sequence = ReadInt64(frame, ref position);
                var length = ReadInt32(frame, ref position);
                if (length < 0 || position + length > frame.Length) throw new FormatException("Queue batch is truncated.");
                byte[] buffer = null; int start = 0, end = 0;
                if (format == EventRecordFormat.Version) { buffer = frame; start = position; end = position + length; }
                else if (format == 0)
                {
                    try
                    {
                        var json = MiniJson.Parse(new UTF8Encoding(false, true).GetString(frame, position, length)) as Dictionary<string, object> ?? throw new FormatException("Queued payload is not an object.");
                        buffer = EventRecordJson.FromJson(json, out _); end = buffer.Length;
                    }
                    catch (Exception) { buffer = null; } // an unreadable legacy row is skipped, not allowed to block the rows behind it; it ages out with the queue limits
                }
                // else: unknown format, skipped the same way
                position += length;
                if (buffer == null) continue;
                batch._sequences[kept] = sequence; batch._buffers[kept] = buffer; batch._starts[kept] = start; batch._ends[kept] = end;
                kept++;
            }
            batch.Count = kept;
            return batch;
        }

        /// <summary>Test seam and migration helper: builds a batch from JSON event payloads (each carrying its "sequence").</summary>
        internal static QueueBatch FromJsonArray(string eventsJson)
        {
            var events = MiniJson.ParseArray(eventsJson);
            var batch = new QueueBatch(events.Count);
            for (var i = 0; i < events.Count; i++)
            {
                var record = EventRecordJson.FromJson(events[i] as Dictionary<string, object> ?? throw new FormatException("event " + i + " is not an object"), out var sequence);
                batch._sequences[i] = sequence; batch._buffers[i] = record; batch._starts[i] = 0; batch._ends[i] = record.Length;
            }
            return batch;
        }

        /// <summary>The batch as a JSON array in the V1 request form; <paramref name="eventIds"/> (same length) replaces the events' own ids when given.</summary>
        internal string ToJsonArray(EventRecordReader reader, IReadOnlyList<string> eventIds = null)
        {
            var json = new StringBuilder(Count * 420 + 2);
            json.Append('[');
            var scratch = _scratch ?? (_scratch = new ParsedEvent());
            for (var i = 0; i < Count; i++)
            {
                if (i > 0) json.Append(',');
                Parse(reader, i, scratch);
                EventRecordJson.Append(json, scratch, eventIds != null ? eventIds[i] : EventId(i), _sequences[i]);
            }
            return json.Append(']').ToString();
        }

        internal static int ReadInt32(byte[] data, ref int position)
        {
            var v = (data[position] << 24) | (data[position + 1] << 16) | (data[position + 2] << 8) | data[position + 3];
            position += 4;
            return v;
        }

        internal static long ReadInt64(byte[] data, ref int position)
        {
            long v = 0;
            for (var i = 0; i < 8; i++) v = (v << 8) | data[position + i];
            position += 8;
            return v;
        }
    }
}
