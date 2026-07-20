using System.Collections.Generic;
using NUnit.Framework;

namespace Daliys.Analytics.Tests
{
    public sealed class AnalyticsTrackTests
    {
        [SetUp]
        public void SetUp()
        {
            Analytics.ResetForTests();
        }

        [Test]
        public void TrackAcceptsFlatPrimitiveProperties()
        {
            Analytics.Initialize(ValidOptions());

            var result = Analytics.Track("level_start", new Dictionary<string, object>
            {
                ["house_id"] = "rome_01",
                ["wave_index"] = 2,
                ["is_first"] = true,
                ["optional_value"] = null
            });

            Assert.That(result, Is.EqualTo(TrackResult.AcceptedToHandoff));
            Assert.That(Analytics.GetDiagnostics().HandoffCount, Is.EqualTo(1));
        }

        [TestCase("sys_session_start")]
        [TestCase("LevelStart")]
        [TestCase("level__start")]
        [TestCase("level_start_")]
        public void TrackRejectsReservedOrInvalidNames(string eventName)
        {
            Analytics.Initialize(ValidOptions());

            Assert.That(Analytics.Track(eventName), Is.EqualTo(TrackResult.InvalidEventName));
        }

        [Test]
        public void TrackRejectsNestedAndNonFiniteProperties()
        {
            Analytics.Initialize(ValidOptions());

            Assert.That(
                Analytics.Track("level_start", new Dictionary<string, object> { ["nested"] = new object() }),
                Is.EqualTo(TrackResult.InvalidProperties));
            Assert.That(
                Analytics.Track("level_start", new Dictionary<string, object> { ["duration"] = double.NaN }),
                Is.EqualTo(TrackResult.InvalidProperties));
        }

        [Test]
        public void HandoffDropsTheNewestEventAtCapacity()
        {
            Analytics.Initialize(ValidOptions());
            for (var index = 0; index < 256; index++)
                Assert.That(Analytics.Track("level_start"), Is.EqualTo(TrackResult.AcceptedToHandoff));

            Assert.That(Analytics.Track("level_start"), Is.EqualTo(TrackResult.HandoffFull));
            Assert.That(Analytics.GetDiagnostics().HandoffDropNewest, Is.EqualTo(1));
        }

        [Test]
        public void FlushMakesItsCurrentLimitationExplicit()
        {
            Analytics.Initialize(ValidOptions());
            Analytics.Track("level_start");

            var result = Analytics.FlushAsync().GetAwaiter().GetResult();

            Assert.That(result.Status, Is.EqualTo(FlushStatus.PersistenceUnavailable));
            Assert.That(result.HandoffEventsPending, Is.EqualTo(1));
        }

        private static AnalyticsOptions ValidOptions()
        {
            return new AnalyticsOptions
            {
                ServerUrl = "https://analytics.example.com",
                ProjectId = "puzzle-development",
                Environment = "development"
            };
        }
    }
}
