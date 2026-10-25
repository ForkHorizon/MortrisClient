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
        internal const byte TagNull = 0, TagFalse = 1, TagTrue = 2, TagInt = 3, TagUInt64 = 4, TagDouble = 5, TagString = 6;
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
        internal static byte[] Build(string appVersion, string buildNumber, string platform, string osVersion, string deviceClass, string locale, int timezoneOffsetMinutes)
        {
            var strings = new[] { appVersion, buildNumber, platform, osVersion, deviceClass, locale };
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

    /// <summary>Builds records. One instance per thread (the buffer is reused); <see cref="Buffer"/> and <see cref="Length"/> are valid until the next Begin.</summary>
    internal sealed class EventRecordWriter
    {
        [ThreadStatic] private static EventRecordWriter _forThread;
        internal static EventRecordWriter ForThread => _forThread ?? (_forThread = new EventRecordWriter());

        private byte[] _buffer = new byte[2048];
        private int _position;
        private int _expected, _count;

        internal byte[] Buffer => _buffer;
        internal int Length => _position;

        internal void Begin(Guid eventId, Guid sessionId, long occurredAtUnixMs, long sessionElapsedMs, byte[] context, string name, int propertyCount)
        {
            _position = 0;
            Ensure(EventRecordFormat.FixedHeader + 40 + context.Length + Encoding.UTF8.GetMaxByteCount(name.Length));
            _buffer[_position++] = EventRecordFormat.Version;
            EventRecordFormat.WriteUuid(_buffer, _position, eventId); _position += 16;
            EventRecordFormat.WriteUuid(_buffer, _position, sessionId); _position += 16;
            EventRecordFormat.WriteVarint(_buffer, ref _position, (ulong)Math.Max(0, occurredAtUnixMs));
            EventRecordFormat.WriteVarint(_buffer, ref _position, (ulong)Math.Max(0, sessionElapsedMs));
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

    internal struct ParsedProperty
    {
        internal string Key;
        internal byte Tag;
        internal long I;
        internal ulong U;
        internal double D;
        internal string S;
    }

    /// <summary>The fields of one record, decoded into reusable storage. Repeated strings (names, keys, context, session id) come from small caches.</summary>
    internal sealed class ParsedEvent
    {
        internal long OccurredAtUnixMs, SessionElapsedMs;
        internal int EventIdOffset, SessionIdOffset;
        internal byte[] Buffer;
        internal string Name, AppVersion, BuildNumber, Platform, OsVersion, DeviceClass, Locale;
        internal int TimezoneOffsetMinutes;
        internal int PropertyCount;
        internal ParsedProperty[] Properties = new ParsedProperty[32];
        internal string SessionIdText;
        internal string EventIdText => EventRecordFormat.UuidText(Buffer, EventIdOffset);
    }

    /// <summary>Decodes records. Not thread-safe (it owns caches); use one per consumer thread.</summary>
    internal sealed class EventRecordReader
    {
        private sealed class Slot { internal int Hash; internal byte[] Bytes; internal string Text; }

        private readonly Slot[] _names = new Slot[256];
        private byte[] _lastContext; private string[] _lastContextStrings; private int _lastTimezone;
        private byte[] _lastSession = new byte[16]; private string _lastSessionText;

        internal void Read(byte[] buffer, int start, int end, ParsedEvent into)
        {
            if (end - start < EventRecordFormat.FixedHeader || buffer[start] != EventRecordFormat.Version) throw new FormatException("Event record has an unknown format.");
            into.Buffer = buffer;
            into.EventIdOffset = start + EventRecordFormat.IdOffset;
            into.SessionIdOffset = start + EventRecordFormat.SessionOffset;
            into.SessionIdText = SessionText(buffer, into.SessionIdOffset);
            var position = start + EventRecordFormat.FixedHeader;
            into.OccurredAtUnixMs = (long)EventRecordFormat.ReadVarint(buffer, ref position, end);
            into.SessionElapsedMs = (long)EventRecordFormat.ReadVarint(buffer, ref position, end);
            var contextLength = (int)EventRecordFormat.ReadVarint(buffer, ref position, end);
            if (contextLength < 0 || position + contextLength > end) throw new FormatException("Event record context is truncated.");
            Context(buffer, position, contextLength, into);
            position += contextLength;
            into.Name = CachedString(buffer, ref position, end);
            var count = (int)EventRecordFormat.ReadVarint(buffer, ref position, end);
            if (count < 0 || count > 1024) throw new FormatException("Event record has an invalid property count.");
            if (into.Properties.Length < count) Array.Resize(ref into.Properties, Math.Max(count, into.Properties.Length * 2));
            into.PropertyCount = count;
            for (var i = 0; i < count; i++)
            {
                ref var p = ref into.Properties[i];
                p.Key = CachedString(buffer, ref position, end);
                if (position >= end) throw new FormatException("Event record is truncated.");
                p.Tag = buffer[position++];
                p.S = null; p.I = 0; p.U = 0; p.D = 0;
                switch (p.Tag)
                {
                    case EventRecordFormat.TagNull: case EventRecordFormat.TagFalse: case EventRecordFormat.TagTrue: break;
                    case EventRecordFormat.TagInt: p.I = EventRecordFormat.UnZigZag(EventRecordFormat.ReadVarint(buffer, ref position, end)); break;
                    case EventRecordFormat.TagUInt64: p.U = EventRecordFormat.ReadVarint(buffer, ref position, end); break;
                    case EventRecordFormat.TagDouble:
                        if (position + 8 > end) throw new FormatException("Event record is truncated.");
                        long bits = 0;
                        for (var b = 0; b < 8; b++) bits |= (long)buffer[position + b] << (8 * b);
                        position += 8;
                        p.D = BitConverter.Int64BitsToDouble(bits);
                        break;
                    case EventRecordFormat.TagString:
                    {
                        var length = (int)EventRecordFormat.ReadVarint(buffer, ref position, end);
                        if (length < 0 || position + length > end) throw new FormatException("Event record string is truncated.");
                        p.S = ValueString(buffer, position, length);
                        position += length;
                        break;
                    }
                    default: throw new FormatException("Event record has an unknown value tag.");
                }
            }
        }

        private string SessionText(byte[] buffer, int offset)
        {
            for (var i = 0; i < 16; i++)
                if (buffer[offset + i] != _lastSession[i]) { Buffer.BlockCopy(buffer, offset, _lastSession, 0, 16); _lastSessionText = null; break; }
            return _lastSessionText ?? (_lastSessionText = EventRecordFormat.UuidText(_lastSession, 0));
        }

        private void Context(byte[] buffer, int offset, int length, ParsedEvent into)
        {
            var same = _lastContext != null && _lastContext.Length == length;
            for (var i = 0; same && i < length; i++) same = _lastContext[i] == buffer[offset + i];
            if (!same)
            {
                var strings = new string[6];
                var position = offset; var end = offset + length;
                for (var i = 0; i < 6; i++)
                {
                    var n = (int)EventRecordFormat.ReadVarint(buffer, ref position, end);
                    if (n < 0 || position + n > end) throw new FormatException("Event record context is truncated.");
                    strings[i] = Encoding.UTF8.GetString(buffer, position, n);
                    position += n;
                }
                _lastTimezone = (int)EventRecordFormat.UnZigZag(EventRecordFormat.ReadVarint(buffer, ref position, end));
                _lastContextStrings = strings;
                _lastContext = new byte[length];
                Buffer.BlockCopy(buffer, offset, _lastContext, 0, length);
            }
            var s = _lastContextStrings;
            into.AppVersion = s[0]; into.BuildNumber = s[1]; into.Platform = s[2]; into.OsVersion = s[3]; into.DeviceClass = s[4]; into.Locale = s[5];
            into.TimezoneOffsetMinutes = _lastTimezone;
        }

        private readonly string[] _values = new string[256];

        /// <summary>String property values repeat a lot (level ids, modes, results): short ASCII ones are looked up by content so a repeat allocates nothing.</summary>
        private string ValueString(byte[] buffer, int position, int length)
        {
            if (length == 0) return string.Empty;
            if (length > 64) return Encoding.UTF8.GetString(buffer, position, length);
            var hash = 17;
            for (var i = 0; i < length; i++)
            {
                var b = buffer[position + i];
                if (b >= 128) return Encoding.UTF8.GetString(buffer, position, length);
                hash = unchecked(hash * 31 + b);
            }
            var index = (hash & 0x7fffffff) % _values.Length;
            var cached = _values[index];
            if (cached != null && cached.Length == length)
            {
                var same = true;
                for (var i = 0; same && i < length; i++) same = cached[i] == buffer[position + i];
                if (same) return cached;
            }
            return _values[index] = Encoding.UTF8.GetString(buffer, position, length);
        }

        private string CachedString(byte[] buffer, ref int position, int end)
        {
            var length = (int)EventRecordFormat.ReadVarint(buffer, ref position, end);
            if (length < 0 || position + length > end) throw new FormatException("Event record string is truncated.");
            var hash = 17;
            for (var i = 0; i < length; i++) hash = unchecked(hash * 31 + buffer[position + i]);
            var index = (hash & 0x7fffffff) % _names.Length;
            var slot = _names[index];
            if (slot != null && slot.Hash == hash && slot.Bytes.Length == length)
            {
                var same = true;
                for (var i = 0; same && i < length; i++) same = slot.Bytes[i] == buffer[position + i];
                if (same) { position += length; return slot.Text; }
            }
            var bytes = new byte[length];
            Buffer.BlockCopy(buffer, position, bytes, 0, length);
            slot = new Slot { Hash = hash, Bytes = bytes, Text = Encoding.UTF8.GetString(bytes) };
            _names[index] = slot;
            position += length;
            return slot.Text;
        }
    }

    /// <summary>JSON forms of a record (V1 request body) and the reverse conversion from queue payloads written by older SDK versions.</summary>
    internal static class EventRecordJson
    {
        private const string TimeFormat = "yyyy-MM-dd'T'HH:mm:ss.fff'Z'";

        /// <summary>One event as the V1 batch API expects it. <paramref name="eventId"/> may be the derived id of an open V7 stream.</summary>
        internal static void Append(StringBuilder json, ParsedEvent e, string eventId, long sequence)
        {
            json.Append("{\"event_id\":"); AppendString(json, eventId);
            json.Append(",\"session_id\":"); AppendString(json, e.SessionIdText);
            json.Append(",\"name\":"); AppendString(json, e.Name);
            json.Append(",\"occurred_at_client\":\"").Append(DateTimeOffset.FromUnixTimeMilliseconds(e.OccurredAtUnixMs).ToString(TimeFormat, CultureInfo.InvariantCulture)).Append('"');
            json.Append(",\"session_elapsed_ms\":").Append(e.SessionElapsedMs.ToString(CultureInfo.InvariantCulture));
            json.Append(",\"app_version\":"); AppendString(json, e.AppVersion);
            json.Append(",\"build_number\":"); AppendString(json, e.BuildNumber);
            json.Append(",\"platform\":"); AppendString(json, e.Platform);
            json.Append(",\"os_version\":"); AppendString(json, e.OsVersion);
            json.Append(",\"device_class\":"); AppendString(json, e.DeviceClass);
            json.Append(",\"locale\":"); AppendString(json, e.Locale);
            json.Append(",\"timezone_offset_minutes\":").Append(e.TimezoneOffsetMinutes.ToString(CultureInfo.InvariantCulture));
            json.Append(",\"properties\":{");
            for (var i = 0; i < e.PropertyCount; i++)
            {
                ref var p = ref e.Properties[i];
                if (i > 0) json.Append(',');
                AppendString(json, p.Key); json.Append(':');
                switch (p.Tag)
                {
                    case EventRecordFormat.TagNull: json.Append("null"); break;
                    case EventRecordFormat.TagFalse: json.Append("false"); break;
                    case EventRecordFormat.TagTrue: json.Append("true"); break;
                    case EventRecordFormat.TagInt: json.Append(p.I.ToString(CultureInfo.InvariantCulture)); break;
                    case EventRecordFormat.TagUInt64: json.Append(p.U.ToString(CultureInfo.InvariantCulture)); break;
                    case EventRecordFormat.TagDouble: json.Append(p.D.ToString("R", CultureInfo.InvariantCulture)); break;
                    default: AppendString(json, p.S); break;
                }
            }
            json.Append("},\"sequence\":").Append(sequence.ToString(CultureInfo.InvariantCulture)).Append('}');
        }

        internal static void AppendString(StringBuilder payload, string value)
        {
            payload.Append('"');
            foreach (var character in value)
            {
                switch (character)
                {
                    case '"': payload.Append("\\\""); break;
                    case '\\': payload.Append("\\\\"); break;
                    case '\b': payload.Append("\\b"); break;
                    case '\f': payload.Append("\\f"); break;
                    case '\n': payload.Append("\\n"); break;
                    case '\r': payload.Append("\\r"); break;
                    case '\t': payload.Append("\\t"); break;
                    default:
                        if (character < ' ') payload.Append("\\u").Append(((int)character).ToString("x4", CultureInfo.InvariantCulture));
                        else payload.Append(character);
                        break;
                }
            }
            payload.Append('"');
        }

        /// <summary>
        /// Converts one queue payload written as JSON (a row stored by an SDK version before binary records, or a test fixture) into a record.
        /// Returns the record bytes (exact length) and the payload's sequence number.
        /// </summary>
        internal static byte[] FromJson(Dictionary<string, object> json, out long sequence)
        {
            var eventId = RequireString(json, "event_id");
            var sessionId = RequireString(json, "session_id");
            var idBytes = new byte[16]; var sessionBytes = new byte[16];
            if (!EventRecordFormat.TryParseUuid(eventId, idBytes, 0) || !EventRecordFormat.TryParseUuid(sessionId, sessionBytes, 0))
                throw new FormatException("event_id and session_id must be UUIDs.");
            sequence = RequireInteger(json, "sequence");
            var timezone = RequireInteger(json, "timezone_offset_minutes");
            if (timezone < int.MinValue || timezone > int.MaxValue) throw new FormatException("timezone_offset_minutes is out of range.");
            if (!DateTimeOffset.TryParseExact(RequireString(json, "occurred_at_client"), TimeFormat, CultureInfo.InvariantCulture,
                    DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var time))
                throw new FormatException("occurred_at_client is invalid.");
            var properties = json.TryGetValue("properties", out var value) ? value as Dictionary<string, object> : null;
            if (properties == null) throw new FormatException("properties must be an object.");

            var context = EventContext.Build(RequireString(json, "app_version"), RequireString(json, "build_number"), RequireString(json, "platform"),
                RequireString(json, "os_version"), RequireString(json, "device_class"), RequireString(json, "locale"), (int)timezone);
            var writer = new EventRecordWriter();
            writer.Begin(Guid.Empty, Guid.Empty, time.ToUnixTimeMilliseconds(), RequireInteger(json, "session_elapsed_ms"), context, RequireString(json, "name"), properties.Count);
            foreach (var property in properties)
            {
                var typed = M7Event.Classify(property.Value, true);
                switch (typed.Type)
                {
                    case M7Catalog.TypeNull: writer.AddNull(property.Key); break;
                    case M7Catalog.TypeBool: writer.AddBool(property.Key, typed.I != 0); break;
                    case M7Catalog.TypeInt: writer.AddInt(property.Key, typed.I); break;
                    case M7Catalog.TypeUInt64: writer.AddUInt64(property.Key, typed.U); break;
                    case M7Catalog.TypeFloat32: case M7Catalog.TypeFloat64: writer.AddRawDouble(property.Key, typed.D); break;
                    default: writer.AddString(property.Key, typed.S); break;
                }
            }
            var length = writer.Finish();
            var record = new byte[length];
            Buffer.BlockCopy(writer.Buffer, 0, record, 0, length);
            Buffer.BlockCopy(idBytes, 0, record, EventRecordFormat.IdOffset, 16);
            Buffer.BlockCopy(sessionBytes, 0, record, EventRecordFormat.SessionOffset, 16);
            return record;
        }

        private static string RequireString(Dictionary<string, object> json, string key) =>
            json.TryGetValue(key, out var value) && value is string text ? text : throw new FormatException("Event field " + key + " must be a string.");

        private static long RequireInteger(Dictionary<string, object> json, string key)
        {
            if (json.TryGetValue(key, out var value) && value is JsonNumber number &&
                long.TryParse(number.Lexeme, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var result))
                return result;
            throw new FormatException("Event field " + key + " must be an integer.");
        }
    }

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
