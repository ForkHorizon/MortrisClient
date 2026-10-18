using System.Collections.Generic;
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    public class IdentityTests
    {
        private const string Install = "3bb427c1-a1da-059d-2ad1-245c92010b38";

        // Pinned by the server's Go tests (internal/transportv7/stream_test.go): both sides must derive the same ids.
        [Theory]
        [InlineData("puzzle_gravity_test", 1, 42, "fdf87015-7deb-4874-baf4-354caa0374dd")]
        [InlineData("puzzle_gravity_test", 2, 42, "d8438cd0-a419-4074-8f03-823157eacdb0")]
        [InlineData("other", 1, 42, "02a18790-d990-4db6-aab2-d7b5a8a84c1c")]
        public void DerivedIdsMatchTheServer(string project, long epoch, long sequence, string expected) =>
            Assert.Equal(expected, V7Identity.DerivedEventId(project, Install, epoch, sequence));

        [Fact]
        public void RewritingReplacesOnlyTheEventIdAndMapsBothWays()
        {
            var queue = new FakeQueue();
            queue.Enqueue(TestSupport.FixtureText("batch-low.json"));
            var batch = queue.ReadOldestBatch(5);
            var rewritten = V7Identity.RewriteEventIds(batch, "synth_indie_runner", queue.InstallId, 3, out var ids);
            var before = MiniJson.ParseArray(batch);
            var after = MiniJson.ParseArray(rewritten);
            Assert.Equal(5, ids.Count);
            for (var i = 0; i < 5; i++)
            {
                var b = (Dictionary<string, object>)before[i];
                var a = (Dictionary<string, object>)after[i];
                Assert.Equal((string)b["event_id"], ids[i].Key);
                Assert.Equal((string)a["event_id"], ids[i].Value);
                Assert.Equal(V7Identity.DerivedEventId("synth_indie_runner", queue.InstallId, 3, i + 1), ids[i].Value);
                b.Remove("event_id"); a.Remove("event_id");
                Assert.Equal(MiniJson.Serialize(b), MiniJson.Serialize(a));           // everything else is untouched, number lexemes included
            }
        }

        [Fact]
        public void SerializeRoundTripsTheFixtures()
        {
            foreach (var name in new[] { "batch-low.json", "batch-high.json", "batch-wide.json" })
            {
                var text = TestSupport.FixtureText(name);
                Assert.Equal(MiniJson.Serialize(MiniJson.Parse(text)), MiniJson.Serialize(MiniJson.Parse(MiniJson.Serialize(MiniJson.Parse(text)))));
            }
        }
    }
}
