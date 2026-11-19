// JSON forms of an event record (V1 request body) and conversion of JSON payloads written by older SDK versions.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Daliys.Analytics.Internal.Transport
{
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
                    case EventRecordFormat.TagSingle: json.Append(((float)p.D).ToString("R", CultureInfo.InvariantCulture)); break;
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

            var context = EventContext.Build((int)timezone, RequireString(json, "app_version"), RequireString(json, "build_number"), RequireString(json, "platform"), RequireString(json, "os_version"), RequireString(json, "device_class"), RequireString(json, "locale"));
            var writer = new EventRecordWriter();
            writer.Begin(new EventHeader(Guid.Empty, Guid.Empty, time.ToUnixTimeMilliseconds(), RequireInteger(json, "session_elapsed_ms"), context), RequireString(json, "name"), properties.Count);
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
}
