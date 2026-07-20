using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Daliys.Analytics.Internal
{
    internal static class PersistenceEventSerializer
    {
        internal static string Serialize(IReadOnlyList<AnalyticsRuntime.TrackedEvent> events, AnalyticsDeviceContext device)
        {
            var payload = new StringBuilder();
            payload.Append('[');
            for (var index = 0; index < events.Count; index++)
            {
                if (index > 0)
                    payload.Append(',');

                var trackedEvent = events[index];
                payload.Append('{');
                AppendProperty(payload, "event_id", trackedEvent.EventId);
                payload.Append(',');
                AppendProperty(payload, "session_id", trackedEvent.SessionId);
                payload.Append(',');
                AppendProperty(payload, "name", trackedEvent.Name);
                payload.Append(',');
                AppendProperty(payload, "occurred_at_client", trackedEvent.OccurredAtClient.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture));
                payload.Append(',');
                AppendProperty(payload, "session_elapsed_ms", trackedEvent.SessionElapsedMilliseconds);
                payload.Append(',');
                AppendProperty(payload, "app_version", device.AppVersion);
                payload.Append(',');
                AppendProperty(payload, "build_number", device.BuildNumber);
                payload.Append(',');
                AppendProperty(payload, "platform", device.Platform);
                payload.Append(',');
                AppendProperty(payload, "os_version", device.OSVersion);
                payload.Append(',');
                AppendProperty(payload, "device_class", device.DeviceClass);
                payload.Append(',');
                AppendProperty(payload, "locale", device.Locale);
                payload.Append(',');
                AppendProperty(payload, "timezone_offset_minutes", device.TimezoneOffsetMinutes);
                payload.Append(',');
                AppendEscapedString(payload, "properties");
                payload.Append(':');
                AppendProperties(payload, trackedEvent.Properties);
                payload.Append('}');
            }
            return payload.Append(']').ToString();
        }

        private static void AppendProperties(StringBuilder payload, IReadOnlyDictionary<string, object> properties)
        {
            payload.Append('{');
            var first = true;
            foreach (var property in properties)
            {
                if (!first)
                    payload.Append(',');
                first = false;
                AppendProperty(payload, property.Key, property.Value);
            }
            payload.Append('}');
        }

        private static void AppendProperty(StringBuilder payload, string name, object value)
        {
            AppendEscapedString(payload, name);
            payload.Append(':');
            AppendValue(payload, value);
        }

        private static void AppendValue(StringBuilder payload, object value)
        {
            switch (value)
            {
                case null:
                    payload.Append("null");
                    return;
                case string text:
                    AppendEscapedString(payload, text);
                    return;
                case bool flag:
                    payload.Append(flag ? "true" : "false");
                    return;
                case float single:
                    payload.Append(single.ToString("R", CultureInfo.InvariantCulture));
                    return;
                case double number:
                    payload.Append(number.ToString("R", CultureInfo.InvariantCulture));
                    return;
                case IFormattable number:
                    payload.Append(number.ToString(null, CultureInfo.InvariantCulture));
                    return;
                default:
                    throw new InvalidOperationException("Unsupported validated event property.");
            }
        }

        private static void AppendEscapedString(StringBuilder payload, string value)
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
                        if (character < ' ')
                            payload.Append("\\u").Append(((int)character).ToString("x4", CultureInfo.InvariantCulture));
                        else
                            payload.Append(character);
                        break;
                }
            }
            payload.Append('"');
        }
    }
}
