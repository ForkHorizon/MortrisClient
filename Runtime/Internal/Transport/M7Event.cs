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

        private static int TextType(string s)
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
