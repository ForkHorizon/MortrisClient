using System;
using System.Collections.Generic;
using NUnit.Framework;
using Daliys.Analytics.Internal;

namespace Daliys.Analytics.Tests
{
    public sealed class PersistenceEventSerializerTests
    {
        [Test]
        public void SerializeWritesTheValidatedFlatEventEnvelope()
        {
            var trackedEvent = new AnalyticsRuntime.TrackedEvent(
                "4e18d837-9ca5-473e-9adb-f403af261ad0",
                "2504f588-5424-476a-b797-1817c7077e46",
                "level_start",
                new Dictionary<string, object>
                {
                    ["house_id"] = "rome_01\nwest",
                    ["wave_index"] = 2,
                    ["is_first"] = true,
                    ["optional_value"] = null
                },
                new DateTimeOffset(2026, 7, 18, 18, 0, 0, TimeSpan.Zero),
                42);

            var device = new AnalyticsDeviceContext("1.2.3", "42", "android", "Android 16", "Pixel", "en-US", 120);
            var json = PersistenceEventSerializer.Serialize(new[] { trackedEvent }, device);

            Assert.That(json, Does.StartWith("[{\"event_id\":\"4e18d837-9ca5-473e-9adb-f403af261ad0\""));
            Assert.That(json, Does.Contain("\"occurred_at_client\":\"2026-07-18T18:00:00.000Z\""));
            Assert.That(json, Does.Contain("\"session_elapsed_ms\":42"));
            Assert.That(json, Does.Contain("\"app_version\":\"1.2.3\""));
            Assert.That(json, Does.Contain("\"house_id\":\"rome_01\\nwest\""));
            Assert.That(json, Does.Contain("\"wave_index\":2"));
            Assert.That(json, Does.Contain("\"is_first\":true"));
            Assert.That(json, Does.Contain("\"optional_value\":null"));
        }
    }
}
