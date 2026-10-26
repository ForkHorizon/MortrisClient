using System;
using System.Collections.Generic;
using System.Globalization;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>One typed property value, classified exactly like the research Python classifier (core._vtype).</summary>
    internal struct M7Value
    {
        internal int Type;
        internal long I;
        internal ulong U;
        internal double D;
        internal string S;
    }

    /// <summary>A queued event parsed from its JSON payload. Properties are sorted by key (ordinal), as shapes are.</summary>
    internal sealed class M7Event
    {
        internal long Sequence;
        internal string SessionId, Name, AppVersion, BuildNumber, Platform, OsVersion, DeviceClass, Locale;
        internal long TimeMs, SessionElapsedMs;
        internal int TimezoneOffsetMinutes;
        internal List<KeyValuePair<string, M7Value>> Properties;

        internal static M7Event Parse(Dictionary<string, object> json, bool logicalStrings)
        {
            var e = new M7Event
            {
                Sequence = RequireInteger(json, "sequence"),
                SessionId = RequireString(json, "session_id"),
                Name = RequireString(json, "name"),
                SessionElapsedMs = RequireInteger(json, "session_elapsed_ms"),
                AppVersion = RequireString(json, "app_version"),
                BuildNumber = RequireString(json, "build_number"),
                Platform = RequireString(json, "platform"),
                OsVersion = RequireString(json, "os_version"),
                DeviceClass = RequireString(json, "device_class"),
                Locale = RequireString(json, "locale"),
            };
            var timezone = RequireInteger(json, "timezone_offset_minutes");
            if (timezone < int.MinValue || timezone > int.MaxValue) throw new FormatException("timezone_offset_minutes is out of range.");
            e.TimezoneOffsetMinutes = (int)timezone;
            if (!DateTimeOffset.TryParseExact(RequireString(json, "occurred_at_client"), "yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture,
                    DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var time))
                throw new FormatException("occurred_at_client is invalid.");
            e.TimeMs = time.ToUnixTimeMilliseconds();
            var properties = json.TryGetValue("properties", out var value) ? value as Dictionary<string, object> : null;
            if (properties == null) throw new FormatException("properties must be an object.");
            e.Properties = new List<KeyValuePair<string, M7Value>>(properties.Count);
            foreach (var property in properties) e.Properties.Add(new KeyValuePair<string, M7Value>(property.Key, Classify(property.Value, logicalStrings)));
            e.Properties.Sort((a, b) => string.CompareOrdinal(a.Key, b.Key));
            return e;
        }

        internal void CopyContextFrom(M7Event e)
        {
            SessionId = e.SessionId; AppVersion = e.AppVersion; BuildNumber = e.BuildNumber; Platform = e.Platform; OsVersion = e.OsVersion; DeviceClass = e.DeviceClass; Locale = e.Locale;
            TimezoneOffsetMinutes = e.TimezoneOffsetMinutes;
        }

        /// <summary>The event of a queue record (the sequence comes from the queue row). Same typing rules as <see cref="Parse"/>.</summary>
        internal static M7Event FromParsed(ParsedEvent p, long sequence, bool logicalStrings, bool typedNumbers = false) => new M7Event().Fill(p, sequence, logicalStrings, typedNumbers);

        /// <summary>Overwrites this event with the parsed one, reusing its property list (the encoder keeps one instance per batch).</summary>
        internal M7Event Fill(ParsedEvent p, long sequence, bool logicalStrings, bool typedNumbers = false)
        {
            var e = this;
            e.Sequence = sequence; e.SessionId = p.SessionIdText; e.Name = p.Name; e.SessionElapsedMs = p.SessionElapsedMs; e.TimeMs = p.OccurredAtUnixMs;
            e.AppVersion = p.AppVersion; e.BuildNumber = p.BuildNumber; e.Platform = p.Platform; e.OsVersion = p.OsVersion; e.DeviceClass = p.DeviceClass; e.Locale = p.Locale;
            e.TimezoneOffsetMinutes = p.TimezoneOffsetMinutes;
            if (e.Properties == null) e.Properties = new List<KeyValuePair<string, M7Value>>(p.PropertyCount); else e.Properties.Clear();
            for (var i = 0; i < p.PropertyCount; i++)
            {
                ref var property = ref p.Properties[i];
                M7Value value;
                switch (property.Tag)
                {
                    case EventRecordFormat.TagNull: value = new M7Value { Type = M7Catalog.TypeNull }; break;
                    case EventRecordFormat.TagFalse: value = new M7Value { Type = M7Catalog.TypeBool }; break;
                    case EventRecordFormat.TagTrue: value = new M7Value { Type = M7Catalog.TypeBool, I = 1 }; break;
                    case EventRecordFormat.TagInt: value = new M7Value { Type = M7Catalog.TypeInt, I = property.I }; break;
                    case EventRecordFormat.TagUInt64: value = new M7Value { Type = M7Catalog.TypeUInt64, U = property.U }; break;
                    case EventRecordFormat.TagDouble:
                        if (double.IsNaN(property.D) || double.IsInfinity(property.D)) throw new FormatException("Non-finite number.");
                        value = new M7Value { Type = typedNumbers ? M7Catalog.TypeFloat64 : (double)(float)property.D == property.D ? M7Catalog.TypeFloat32 : M7Catalog.TypeFloat64, D = property.D };
                        break;
                    case EventRecordFormat.TagSingle:
                        if (double.IsNaN(property.D) || double.IsInfinity(property.D)) throw new FormatException("Non-finite number.");
                        // typed (V8): a float32 stays float32. Otherwise it is read as the JSON path always read a float: its shortest text decides int, float32 or float64.
                        value = typedNumbers ? new M7Value { Type = M7Catalog.TypeFloat32, D = property.D } : ClassifyNumber(((float)property.D).ToString("R", CultureInfo.InvariantCulture));
                        break;
                    default: value = new M7Value { Type = logicalStrings ? M7Catalog.TypeString : TextType(property.S), S = property.S }; break;
                }
                e.Properties.Add(new KeyValuePair<string, M7Value>(property.Key, value));
            }
            e.Properties.Sort(CompareKeys);
            return e;
        }

        private static readonly Comparison<KeyValuePair<string, M7Value>> CompareKeys = (a, b) => string.CompareOrdinal(a.Key, b.Key);

        /// <summary>
        /// Type of a JSON value: null, bool, integer lexeme (int64, else uint64), other number (float32 when exactly
        /// representable, else float64), string (uuid or hex when the catalog does not use logical strings, else string).
        /// </summary>
        internal static M7Value Classify(object value, bool logicalStrings)
        {
            switch (value)
            {
                case null: return new M7Value { Type = M7Catalog.TypeNull };
                case bool flag: return new M7Value { Type = M7Catalog.TypeBool, I = flag ? 1 : 0 };
                case string text: return new M7Value { Type = logicalStrings ? M7Catalog.TypeString : TextType(text), S = text };
                case JsonNumber number: return ClassifyNumber(number.Lexeme);
                default: throw new FormatException("Unsupported property value.");
            }
        }

        private static M7Value ClassifyNumber(string lexeme)
        {
            var integer = true;
            for (var i = 0; i < lexeme.Length; i++)
                if (lexeme[i] == '.' || lexeme[i] == 'e' || lexeme[i] == 'E') { integer = false; break; }
            if (integer)
            {
                if (long.TryParse(lexeme, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var signed)) return new M7Value { Type = M7Catalog.TypeInt, I = signed };
                if (ulong.TryParse(lexeme, NumberStyles.None, CultureInfo.InvariantCulture, out var unsigned)) return new M7Value { Type = M7Catalog.TypeUInt64, U = unsigned };
                throw new FormatException("Integer is outside the 64-bit domain.");
            }
            var d = double.Parse(lexeme, NumberStyles.Float, CultureInfo.InvariantCulture);
            if (double.IsNaN(d) || double.IsInfinity(d)) throw new FormatException("Non-finite number.");
            var exactSingle = (double)(float)d == d;
            return new M7Value { Type = exactSingle ? M7Catalog.TypeFloat32 : M7Catalog.TypeFloat64, D = d };
        }

        internal static int TextType(string s)
        {
            if (s.Length == 36 && IsUuid(s)) return M7Catalog.TypeUuid;
            if (s.Length >= 16 && (s.Length & 1) == 0 && IsLowerHex(s, 0, s.Length)) return M7Catalog.TypeHex;
            return M7Catalog.TypeString;
        }

        private static bool IsUuid(string s)
        {
            for (var i = 0; i < 36; i++)
            {
                if (i == 8 || i == 13 || i == 18 || i == 23) { if (s[i] != '-') return false; }
                else if (!IsLowerHexChar(s[i])) return false;
            }
            return true;
        }

        private static bool IsLowerHex(string s, int from, int to)
        {
            for (var i = from; i < to; i++) if (!IsLowerHexChar(s[i])) return false;
            return true;
        }

        private static bool IsLowerHexChar(char c) => (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');

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
}
