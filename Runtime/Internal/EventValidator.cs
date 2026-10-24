using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Daliys.Analytics.Internal
{
    internal static class EventValidator
    {
        internal const int MaxPropertyCount = 32;
        internal const int MaxEventNameLength = 64;
        internal const int MaxPropertyKeyBytes = 64;
        internal const int MaxPropertyValueBytes = 1024;
        internal const int MaxPropertiesBytes = 8 * 1024;

        internal static bool IsValidPublicEventName(string eventName)
        {
            return IsSnakeCaseIdentifier(eventName, MaxEventNameLength) &&
                   !eventName.StartsWith("sys_", StringComparison.Ordinal);
        }

        internal static bool HasValidProperties(IReadOnlyDictionary<string, object> properties)
        {
            if (properties == null)
                return true;

            if (properties.Count > MaxPropertyCount)
                return false;

            // Dictionary is what callers pass; its struct enumerator avoids the boxed one an interface foreach allocates on every Track.
            if (properties is Dictionary<string, object> map)
            {
                var characters = 0L;
                foreach (var property in map)
                {
                    if (!IsValidProperty(property.Key, property.Value))
                        return false;
                    characters += property.Key.Length + (property.Value is string text ? text.Length : 0);
                }
                // Every character escapes to at most 6 bytes and a number is at most 40: when even that bound fits, the exact estimate cannot exceed the limit.
                if (2 + 6 * characters + 50L * map.Count <= MaxPropertiesBytes)
                    return true;
                return EstimateEncodedPropertiesBytes(map) <= MaxPropertiesBytes;
            }

            foreach (var property in properties)
                if (!IsValidProperty(property.Key, property.Value))
                    return false;
            return EstimateEncodedPropertiesBytes(properties) <= MaxPropertiesBytes;
        }

        private static bool IsValidProperty(string key, object value) =>
            IsSnakeCaseIdentifier(key, MaxPropertyKeyBytes) &&
            Encoding.UTF8.GetByteCount(key) <= MaxPropertyKeyBytes &&
            IsSupportedValue(value) &&
            !(value is string text && Encoding.UTF8.GetByteCount(text) > MaxPropertyValueBytes);

        internal static bool IsSupportedValue(object value)
        {
            switch (value)
            {
                case null:
                case string:
                case bool:
                case sbyte:
                case byte:
                case short:
                case ushort:
                case int:
                case uint:
                case long:
                case ulong:
                case decimal:
                    return true;
                case float single:
                    return !float.IsNaN(single) && !float.IsInfinity(single);
                case double number:
                    return !double.IsNaN(number) && !double.IsInfinity(number);
                default:
                    return false;
            }
        }

        private static bool IsSnakeCaseIdentifier(string value, int maxLength)
        {
            if (string.IsNullOrEmpty(value) || value.Length > maxLength || value[0] < 'a' || value[0] > 'z' || value[value.Length - 1] == '_')
                return false;

            var previousUnderscore = false;
            foreach (var character in value)
            {
                var allowed = (character >= 'a' && character <= 'z') ||
                              (character >= '0' && character <= '9') ||
                              character == '_';
                if (!allowed || (character == '_' && previousUnderscore))
                    return false;

                previousUnderscore = character == '_';
            }

            return true;
        }

        // Go's encoding/json escapes HTML-significant characters, so this is a
        // conservative byte count for the server's 8 KiB encoded-object limit.
        private static int EstimateEncodedPropertiesBytes(IReadOnlyDictionary<string, object> properties)
        {
            var bytes = 2; // {}
            var first = true;
            foreach (var property in properties)
            {
                if (!first)
                    bytes++;
                first = false;
                bytes += 2 + EscapedStringBytes(property.Key) + 1;
                bytes += ValueBytes(property.Value);
                if (bytes > MaxPropertiesBytes)
                    return bytes;
            }
            return bytes;
        }

        private static int EstimateEncodedPropertiesBytes(Dictionary<string, object> properties)
        {
            var bytes = 2; // {}
            var first = true;
            foreach (var property in properties)
            {
                if (!first)
                    bytes++;
                first = false;
                bytes += 2 + EscapedStringBytes(property.Key) + 1;
                bytes += ValueBytes(property.Value);
                if (bytes > MaxPropertiesBytes)
                    return bytes;
            }
            return bytes;
        }

        private static int ValueBytes(object value)
        {
            if (value == null)
                return 4;
            if (value is string text)
                return 2 + EscapedStringBytes(text);
            if (value is bool flag)
                return flag ? 4 : 5;
            return NumberChars(value);
        }

        /// <summary>Length of the number's invariant text (all ASCII), formatted into stack space instead of a new string.</summary>
        private static int NumberChars(object value)
        {
            Span<char> buffer = stackalloc char[64];
            int written;
            bool ok;
            switch (value)
            {
                case int v: ok = v.TryFormat(buffer, out written, default, CultureInfo.InvariantCulture); break;
                case long v: ok = v.TryFormat(buffer, out written, default, CultureInfo.InvariantCulture); break;
                case double v: ok = v.TryFormat(buffer, out written, "R", CultureInfo.InvariantCulture); break;
                case float v: ok = v.TryFormat(buffer, out written, "R", CultureInfo.InvariantCulture); break;
                case uint v: ok = v.TryFormat(buffer, out written, default, CultureInfo.InvariantCulture); break;
                case ulong v: ok = v.TryFormat(buffer, out written, default, CultureInfo.InvariantCulture); break;
                case short v: ok = v.TryFormat(buffer, out written, default, CultureInfo.InvariantCulture); break;
                case ushort v: ok = v.TryFormat(buffer, out written, default, CultureInfo.InvariantCulture); break;
                case byte v: ok = v.TryFormat(buffer, out written, default, CultureInfo.InvariantCulture); break;
                case sbyte v: ok = v.TryFormat(buffer, out written, default, CultureInfo.InvariantCulture); break;
                case decimal v: ok = v.TryFormat(buffer, out written, default, CultureInfo.InvariantCulture); break;
                default: return Encoding.UTF8.GetByteCount(((IFormattable)value).ToString(null, CultureInfo.InvariantCulture));
            }
            return ok ? written : Encoding.UTF8.GetByteCount(((IFormattable)value).ToString(null, CultureInfo.InvariantCulture));
        }

        private static int EscapedStringBytes(string value)
        {
            var bytes = 0;
            for (var index = 0; index < value.Length; index++)
            {
                var character = value[index];
                if (character == '"' || character == '\\' || character == '\b' || character == '\f' ||
                    character == '\n' || character == '\r' || character == '\t')
                {
                    bytes += 2;
                }
                else if (character < ' ' || character == '<' || character == '>' || character == '&' ||
                         character == '\u2028' || character == '\u2029')
                {
                    bytes += 6;
                }
                else if (character < 0x80)
                {
                    bytes += 1;
                }
                else if (character < 0x800)
                {
                    bytes += 2;
                }
                else
                {
                    bytes += 3; // BMP characters above 0x7FF; a surrogate is counted per half (3 + 3), deliberately above its real 4 bytes: the limit stays conservative
                }
            }
            return bytes;
        }
    }
}
