using System;
using System.IO;
using NUnit.Framework;

namespace Daliys.Analytics.Internal
{
    public sealed class AnalyticsUploaderTests
    {
        [Test]
        public void ParseAcknowledgementAcceptsEverySentEventExactlyOnce()
        {
            var acknowledgement = AnalyticsUploader.ParseAcknowledgement(
                "{\"server_time\":\"2026-07-19T12:00:00.000Z\",\"accepted\":[\"a\"],\"duplicates\":[\"b\"],\"rejected\":[{\"event_id\":\"c\",\"code\":\"invalid_event_name\"}],\"client_policy\":{\"mode\":\"active\",\"next_check_seconds\":1,\"discard_pending\":false}}",
                new[] { "a", "b", "c" });

            Assert.That(acknowledgement.EventIds, Is.EquivalentTo(new[] { "a", "b", "c" }));
            Assert.That(acknowledgement.Policy.Mode, Is.EqualTo(ServerPolicyMode.Active));
            Assert.That(acknowledgement.Policy.NextCheckSeconds, Is.EqualTo(300));
        }

        [Test]
        public void ParseAcknowledgementRetainsAnOmittedSentEvent()
        {
            const string response = "{\"server_time\":\"2026-07-19T12:00:00.000Z\",\"accepted\":[\"a\"],\"duplicates\":[],\"rejected\":[],\"client_policy\":{\"mode\":\"active\",\"next_check_seconds\":300,\"discard_pending\":false}}";

            var acknowledgement = AnalyticsUploader.ParseAcknowledgement(response, new[] { "a", "b" });

            Assert.That(acknowledgement.EventIds, Is.EquivalentTo(new[] { "a" }));
        }

        [Test]
        public void ParseAcknowledgementRejectsARejectionWithoutStableCode()
        {
            const string response = "{\"server_time\":\"2026-07-19T12:00:00.000Z\",\"accepted\":[],\"duplicates\":[],\"rejected\":[{\"event_id\":\"a\"}],\"client_policy\":{\"mode\":\"active\",\"next_check_seconds\":300,\"discard_pending\":false}}";

            Assert.Throws<InvalidDataException>(() => AnalyticsUploader.ParseAcknowledgement(response, new[] { "a" }));
        }
    }
}
