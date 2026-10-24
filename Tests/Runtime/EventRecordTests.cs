using System;
using System.Collections.Generic;
using System.Text;
using Daliys.Analytics.Internal;
using Daliys.Analytics.Internal.Transport;
using NUnit.Framework;

namespace Daliys.Analytics.Tests
{
    /// <summary>Runs the record path under Unity's runtime (Mono / IL2CPP number formatting, UTF-8 and Guid behaviour are the runtime's, not the host's).</summary>
    public sealed class EventRecordTests
    {
        [Test]
        public void RecordRendersTheValidatedFlatEventEnvelopeAsV1Json()
        {
            var id = new Guid("4e18d837-9ca5-473e-9adb-f403af261ad0");
            var session = new Guid("2504f588-5424-476a-b797-1817c7077e46");
            var device = new AnalyticsDeviceContext("1.2.3", "42", "android", "Android 16", "Pixel", "en-US", 120);
            var context = EventContext.Build(device.AppVersion, device.BuildNumber, device.Platform, device.OSVersion, device.DeviceClass, device.Locale, device.TimezoneOffsetMinutes);
            var properties = new Dictionary<string, object>
            {
                ["house_id"] = "rome_01\nwest", ["wave_index"] = 2, ["is_first"] = true, ["optional_value"] = null, ["ratio"] = 0.25, ["total"] = 3.0,
            };
            var writer = new EventRecordWriter();
            writer.Begin(id, session, new DateTimeOffset(2026, 7, 18, 18, 0, 0, TimeSpan.Zero).ToUnixTimeMilliseconds(), 42, context, "level_start", properties.Count);
            foreach (var property in properties) writer.AddClr(property.Key, property.Value);
            var record = new byte[writer.Finish()];
            Buffer.BlockCopy(writer.Buffer, 0, record, 0, record.Length);

            var parsed = new ParsedEvent();
            new EventRecordReader().Read(record, 0, record.Length, parsed);
            var json = new StringBuilder();
            EventRecordJson.Append(json, parsed, parsed.EventIdText, 7);
            var text = json.ToString();

            Assert.That(text, Does.StartWith("{\"event_id\":\"4e18d837-9ca5-473e-9adb-f403af261ad0\""));
            Assert.That(text, Does.Contain("\"occurred_at_client\":\"2026-07-18T18:00:00.000Z\""));
            Assert.That(text, Does.Contain("\"session_elapsed_ms\":42"));
            Assert.That(text, Does.Contain("\"app_version\":\"1.2.3\""));
            Assert.That(text, Does.Contain("\"house_id\":\"rome_01\\nwest\""));
            Assert.That(text, Does.Contain("\"wave_index\":2"));
            Assert.That(text, Does.Contain("\"is_first\":true"));
            Assert.That(text, Does.Contain("\"optional_value\":null"));
            Assert.That(text, Does.Contain("\"ratio\":0.25"));
            Assert.That(text, Does.Contain("\"total\":3"));
            Assert.That(text, Does.EndWith("\"sequence\":7}"));
        }

        [Test]
        public void IntegralDoublesAreIntegersLikeTheJsonPathOnThisRuntime()
        {
            foreach (var value in new[] { 0.0, 3.0, -7.0, 999999999999999.0 })
            {
                var writer = new EventRecordWriter();
                writer.Begin(Guid.NewGuid(), Guid.NewGuid(), 1, 0, EventContext.Build("a", "b", "c", "d", "e", "f", 0), "e", 1);
                writer.AddDouble("n", value);
                var record = new byte[writer.Finish()];
                Buffer.BlockCopy(writer.Buffer, 0, record, 0, record.Length);
                var parsed = new ParsedEvent();
                new EventRecordReader().Read(record, 0, record.Length, parsed);
                // the old serializer wrote value.ToString("R"); an integer lexeme on this runtime means an integer record
                var lexeme = value.ToString("R", System.Globalization.CultureInfo.InvariantCulture);
                var integerLexeme = lexeme.IndexOfAny(new[] { '.', 'E', 'e' }) < 0;
                Assert.That(parsed.Properties[0].Tag == EventRecordFormat.TagInt, Is.EqualTo(integerLexeme), "value " + lexeme);
            }
        }
    }
}
