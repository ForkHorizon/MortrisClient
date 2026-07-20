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

            foreach (var property in properties)
            {
                if (!IsSnakeCaseIdentifier(property.Key, MaxPropertyKeyBytes) ||
                    Encoding.UTF8.GetByteCount(property.Key) > MaxPropertyKeyBytes ||
                    !IsSupportedValue(property.Value) ||
                    (property.Value is string text && Encoding.UTF8.GetByteCount(text) > MaxPropertyValueBytes))
                    return false;
            }

            return EstimateEncodedPropertiesBytes(properties) <= MaxPropertiesBytes;
        }

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

        private static int ValueBytes(object value)
        {
            if (value == null)
                return 4;
            if (value is string text)
                return 2 + EscapedStringBytes(text);
            if (value is bool flag)
                return flag ? 4 : 5;
            return Encoding.UTF8.GetByteCount(((IFormattable)value).ToString(null, CultureInfo.InvariantCulture));
        }

        private static int EscapedStringBytes(string value)
        {
            var bytes = 0;
            foreach (var character in value)
            {
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
                else
                {
                    bytes += Encoding.UTF8.GetByteCount(character.ToString());
                }
            }
            return bytes;
        }
    }
}
