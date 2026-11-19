// Decodes binary event records into reusable storage (ParsedEvent), with small caches for repeated strings.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Daliys.Analytics.Internal.Transport
{
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
                    case EventRecordFormat.TagSingle:
                        if (position + 4 > end) throw new FormatException("Event record is truncated.");
                        p.D = BitConverter.Int32BitsToSingle(buffer[position] | buffer[position + 1] << 8 | buffer[position + 2] << 16 | buffer[position + 3] << 24);
                        position += 4;
                        break;
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
}
