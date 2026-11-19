// Binary form of one tracked event, written once on Track() and read by every transport.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>
    /// Binary form of one tracked event, written once on <c>Track()</c> and read by both transports (V7 columns, V1 JSON), so no stage
    /// has to build or parse JSON text. Layout (little-endian varints, UTF-8 strings):
    /// <code>
    /// u8 format(=1) | 16B event id (canonical UUID byte order) | 16B session id | varint occurred_at_unix_ms | varint session_elapsed_ms |
    /// varint ctx_len, ctx bytes (6 strings + zigzag timezone, see EventContext) | string name | varint property_count |
    /// property*: string key, u8 tag, value
    /// tags: 0 null | 1 false | 2 true | 3 int64 (zigzag varint) | 4 uint64 (varint) | 5 float64 (8 bytes) | 6 string
    /// </code>
    /// The sequence number is not part of the record: the queue assigns it and hands it back next to the record.
    /// Numbers are classified exactly like the JSON lexeme rule of the V1 path (an integral double is an integer, see <see cref="EventRecordWriter.AddDouble"/>).
    /// </summary>
    internal static class EventRecordFormat
    {
        internal const byte Version = 1;
        internal const byte TagNull = 0, TagFalse = 1, TagTrue = 2, TagInt = 3, TagUInt64 = 4, TagDouble = 5, TagString = 6, TagSingle = 7;
        internal const int IdOffset = 1, SessionOffset = 17, FixedHeader = 33;

        internal static void WriteVarint(byte[] buffer, ref int position, ulong value)
        {
            while (value >= 128) { buffer[position++] = (byte)(value | 128); value >>= 7; }
            buffer[position++] = (byte)value;
        }

        internal static ulong ReadVarint(byte[] buffer, ref int position, int end)
        {
            ulong result = 0;
            for (var shift = 0; shift < 70; shift += 7)
            {
                if (position >= end) throw new FormatException("Event record is truncated.");
                var b = buffer[position++];
                if (shift == 63 && b > 1) throw new FormatException("Event record has an invalid varint.");
                result |= (ulong)(b & 127) << shift;
                if (b < 128) return result;
            }
            throw new FormatException("Event record has an invalid varint.");
        }

        internal static ulong ZigZag(long value) => unchecked((ulong)((value << 1) ^ (value >> 63)));
        internal static long UnZigZag(ulong value) => unchecked((long)(value >> 1) ^ -(long)(value & 1));

        /// <summary>Writes a UUID in canonical (RFC 4122) byte order, i.e. the order of its "D" text form.</summary>
        internal static void WriteUuid(byte[] buffer, int position, Guid id)
        {
            Span<byte> little = stackalloc byte[16];
            id.TryWriteBytes(little);
            buffer[position] = little[3]; buffer[position + 1] = little[2]; buffer[position + 2] = little[1]; buffer[position + 3] = little[0];
            buffer[position + 4] = little[5]; buffer[position + 5] = little[4];
            buffer[position + 6] = little[7]; buffer[position + 7] = little[6];
            for (var i = 8; i < 16; i++) buffer[position + i] = little[i];
        }

        internal static Guid ReadUuid(byte[] buffer, int position)
        {
            var little = new byte[16];
            little[3] = buffer[position]; little[2] = buffer[position + 1]; little[1] = buffer[position + 2]; little[0] = buffer[position + 3];
            little[5] = buffer[position + 4]; little[4] = buffer[position + 5];
            little[7] = buffer[position + 6]; little[6] = buffer[position + 7];
            Buffer.BlockCopy(buffer, position + 8, little, 8, 8);
            return new Guid(little);
        }

        private const string Hex = "0123456789abcdef";

        /// <summary>The "D" text form (lowercase, dashed) of the 16 bytes at <paramref name="position"/>.</summary>
        internal static string UuidText(byte[] buffer, int position)
        {
            var chars = new char[36];
            var o = 0;
            for (var i = 0; i < 16; i++)
            {
                if (i == 4 || i == 6 || i == 8 || i == 10) chars[o++] = '-';
                var b = buffer[position + i];
                chars[o++] = Hex[b >> 4];
                chars[o++] = Hex[b & 15];
            }
            return new string(chars);
        }

        /// <summary>Parses a lowercase or uppercase dashed UUID into 16 bytes; false when it is not one.</summary>
        internal static bool TryParseUuid(string text, byte[] destination, int position)
        {
            if (text == null || text.Length != 36) return false;
            var o = 0;
            for (var i = 0; i < 36;)
            {
                if (i == 8 || i == 13 || i == 18 || i == 23) { if (text[i] != '-') return false; i++; continue; }
                var hi = HexValue(text[i]); var lo = HexValue(text[i + 1]);
                if (hi < 0 || lo < 0) return false;
                destination[position + o++] = (byte)((hi << 4) | lo);
                i += 2;
            }
            return true;
        }

        private static int HexValue(char c) => c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
    }

    /// <summary>The device fields every event of a process carries, encoded once: 6 strings (varint length + UTF-8) and the zigzag timezone offset.</summary>
    internal static class EventContext
    {
        /// <summary><paramref name="fields"/>: app version, build number, platform, OS version, device class, locale (in this order).</summary>
        internal static byte[] Build(int timezoneOffsetMinutes, params string[] fields)
        {
            if (fields == null || fields.Length != 6) throw new ArgumentException("An event context has six fields.", nameof(fields));
            var strings = fields;
            var size = 10;
            foreach (var s in strings) size += 5 + Encoding.UTF8.GetByteCount(s);
            var buffer = new byte[size];
            var position = 0;
            foreach (var s in strings)
            {
                var count = Encoding.UTF8.GetByteCount(s);
                EventRecordFormat.WriteVarint(buffer, ref position, (ulong)count);
                position += Encoding.UTF8.GetBytes(s, 0, s.Length, buffer, position);
            }
            EventRecordFormat.WriteVarint(buffer, ref position, EventRecordFormat.ZigZag(timezoneOffsetMinutes));
            var exact = new byte[position];
            Buffer.BlockCopy(buffer, 0, exact, 0, position);
            return exact;
        }
    }

    /// <summary>The fixed fields that open every record (a value type: building one allocates nothing).</summary>
    internal readonly struct EventHeader
    {
        internal readonly Guid EventId, SessionId;
        internal readonly long OccurredAtUnixMs, SessionElapsedMs;
        internal readonly byte[] Context;

        internal EventHeader(Guid eventId, Guid sessionId, long occurredAtUnixMs, long sessionElapsedMs, byte[] context)
        {
            EventId = eventId; SessionId = sessionId; OccurredAtUnixMs = occurredAtUnixMs; SessionElapsedMs = sessionElapsedMs; Context = context;
        }
    }

    /// <summary>Builds records. One instance per thread (the buffer is reused); <see cref="Buffer"/> and <see cref="Length"/> are valid until the next Begin.</summary>
    internal sealed class EventRecordWriter
    {
        [ThreadStatic] private static EventRecordWriter _forThread;
        internal static EventRecordWriter ForThread => _forThread ?? (_forThread = new EventRecordWriter());

        /// <summary>
        /// V8 mode: numbers keep the type they have in the game. A float is a float32 and a double a float64 whatever their value, so an event's shape does
        /// not change when a float happens to be 0 or 0.5. When off (V1 and V7) the type is derived from the value, as the JSON path always did.
        /// </summary>
        internal bool TypedNumbers;

        private byte[] _buffer = new byte[2048];
        private int _position;
        private int _expected, _count;

        internal byte[] Buffer => _buffer;
        internal int Length => _position;

        internal void Begin(EventHeader header, string name, int propertyCount)
        {
            var context = header.Context;
            _position = 0;
            Ensure(EventRecordFormat.FixedHeader + 40 + context.Length + Encoding.UTF8.GetMaxByteCount(name.Length));
            _buffer[_position++] = EventRecordFormat.Version;
            EventRecordFormat.WriteUuid(_buffer, _position, header.EventId); _position += 16;
            EventRecordFormat.WriteUuid(_buffer, _position, header.SessionId); _position += 16;
            EventRecordFormat.WriteVarint(_buffer, ref _position, (ulong)Math.Max(0, header.OccurredAtUnixMs));
            EventRecordFormat.WriteVarint(_buffer, ref _position, (ulong)Math.Max(0, header.SessionElapsedMs));
            EventRecordFormat.WriteVarint(_buffer, ref _position, (ulong)context.Length);
            System.Buffer.BlockCopy(context, 0, _buffer, _position, context.Length); _position += context.Length;
            WriteString(name);
            EventRecordFormat.WriteVarint(_buffer, ref _position, (ulong)propertyCount);
            _expected = propertyCount;
            _count = 0;
        }

        /// <summary>Ends the record; the number of added properties must be the one announced in Begin.</summary>
        internal int Finish()
        {
            if (_count != _expected) throw new InvalidOperationException("Event record property count mismatch.");
            return _position;
        }

        internal void AddNull(string key) { Key(key, EventRecordFormat.TagNull); }
        internal void AddBool(string key, bool value) { Key(key, value ? EventRecordFormat.TagTrue : EventRecordFormat.TagFalse); }
        internal void AddInt(string key, long value) { Key(key, EventRecordFormat.TagInt); Ensure(10); EventRecordFormat.WriteVarint(_buffer, ref _position, EventRecordFormat.ZigZag(value)); }
        internal void AddUInt64(string key, ulong value) { Key(key, EventRecordFormat.TagUInt64); Ensure(10); EventRecordFormat.WriteVarint(_buffer, ref _position, value); }
        internal void AddRawDouble(string key, double value)
        {
            Key(key, EventRecordFormat.TagDouble); Ensure(8);
            var bits = BitConverter.DoubleToInt64Bits(value);
            for (var i = 0; i < 8; i++) _buffer[_position++] = (byte)(bits >> (8 * i));
        }

        internal void AddString(string key, string value)
        {
            Key(key, EventRecordFormat.TagString);
            WriteString(value);
        }

        /// <summary>
        /// A double as the V1 JSON path sees it: its "R" text is an integer lexeme (no '.', 'e', 'E') exactly when the value is integral and below 1e15 in magnitude
        /// (above that "R" switches to exponent form); such values are integers, everything else stays a double.
        /// </summary>
        internal void AddDouble(string key, double value)
        {
            if (TypedNumbers) { AddRawDouble(key, value); return; }
            if (value == Math.Floor(value) && Math.Abs(value) < 1e15) AddInt(key, (long)value);
            else AddRawDouble(key, value);
        }

        private static readonly double[] Pow10 = { 1, 1e1, 1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e11, 1e12, 1e13, 1e14, 1e15, 1e16, 1e17, 1e18, 1e19, 1e20, 1e21, 1e22 };

        /// <summary>
        /// A float32 is classified through its shortest round-trip text, like the JSON path. The common values are handled without building that text:
        /// small integral floats are integers, and a float whose shortest text has at most 7 digits is that decimal divided exactly (mantissa and power of ten
        /// are exact doubles, so the division rounds like a parse would); everything else takes the text route.
        /// </summary>
        internal void AddSingle(string key, float value)
        {
            if (TypedNumbers)
            {
                if (float.IsNaN(value) || float.IsInfinity(value)) throw new InvalidOperationException("Non-finite number.");
                Key(key, EventRecordFormat.TagSingle); Ensure(4);
                var bits = BitConverter.SingleToInt32Bits(value);
                for (var i = 0; i < 4; i++) _buffer[_position++] = (byte)(bits >> (8 * i));
                return;
            }
            if (value == (float)Math.Floor(value) && Math.Abs(value) < 1e7f) { AddInt(key, (long)value); return; }
            if (TryShortestDouble(value, out var d)) { AddRawDouble(key, d); return; }
            AddLexeme(key, value.ToString("R", CultureInfo.InvariantCulture));
        }

        internal static bool TryShortestDouble(float value, out double result)
        {
            result = 0;
            var magnitude = Math.Abs((double)value);
            if (!(magnitude >= 1e-5 && magnitude < 1e7)) return false; // also NaN and infinities
            // The fewest decimal places that read back as this float: that is the shortest text. m and the power of ten are exact doubles, so the division is
            // correctly rounded, like parsing the text would be.
            for (var scale = 1; scale <= 11; scale++)
            {
                var m = Math.Round(magnitude * Pow10[scale]);
                if (m >= 1e7 || m < 1) return false; // more than 7 digits: leave it to the text route
                var d = m / Pow10[scale];
                if ((float)d == magnitude)
                {
                    result = value < 0 ? -d : d;
                    return true;
                }
            }
            return false;
        }

        /// <summary>A number given as its text (decimal, float): integer lexemes become integers, anything else a double.</summary>
        internal void AddLexeme(string key, string lexeme)
        {
            var integer = true;
            for (var i = 0; i < lexeme.Length; i++) if (lexeme[i] == '.' || lexeme[i] == 'e' || lexeme[i] == 'E') { integer = false; break; }
            if (integer)
            {
                if (long.TryParse(lexeme, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var signed)) { AddInt(key, signed); return; }
                if (ulong.TryParse(lexeme, NumberStyles.None, CultureInfo.InvariantCulture, out var unsigned)) { AddUInt64(key, unsigned); return; }
            }
            AddRawDouble(key, double.Parse(lexeme, NumberStyles.Float, CultureInfo.InvariantCulture));
        }

        /// <summary>Adds a validated public property value (see EventValidator.IsSupportedValue).</summary>
        internal void AddClr(string key, object value)
        {
            switch (value)
            {
                case null: AddNull(key); break;
                case string text: AddString(key, text); break;
                case bool flag: AddBool(key, flag); break;
                case int i: AddInt(key, i); break;
                case long l: AddInt(key, l); break;
                case double d: AddDouble(key, d); break;
                case float f: AddSingle(key, f); break;
                case sbyte sb: AddInt(key, sb); break;
                case byte b: AddInt(key, b); break;
                case short s: AddInt(key, s); break;
                case ushort us: AddInt(key, us); break;
                case uint ui: AddInt(key, ui); break;
                case ulong ul: if (ul <= long.MaxValue) AddInt(key, (long)ul); else AddUInt64(key, ul); break;
                case decimal m: AddLexeme(key, m.ToString(CultureInfo.InvariantCulture)); break;
                default: throw new InvalidOperationException("Unsupported validated event property.");
            }
        }

        private void Key(string key, byte tag)
        {
            Ensure(Encoding.UTF8.GetMaxByteCount(key.Length) + 12);
            WriteString(key);
            _buffer[_position++] = tag;
            _count++;
        }

        private void WriteString(string value)
        {
            var count = Encoding.UTF8.GetByteCount(value);
            Ensure(count + 6);
            EventRecordFormat.WriteVarint(_buffer, ref _position, (ulong)count);
            _position += Encoding.UTF8.GetBytes(value, 0, value.Length, _buffer, _position);
        }

        private void Ensure(int extra)
        {
            if (_position + extra <= _buffer.Length) return;
            var size = _buffer.Length;
            while (size < _position + extra) size *= 2;
            Array.Resize(ref _buffer, size);
        }
    }
}
