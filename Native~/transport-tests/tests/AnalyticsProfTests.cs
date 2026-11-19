// Tests for the profiling stage timers (AnalyticsProf).
using System;
using System.Linq;
using System.Threading;
using Daliys.Analytics.Internal;
using Xunit;

namespace M7Transport.Tests
{
    public class AnalyticsProfTests
    {
        [Fact]
        public void EveryStageHasAName()
        {
            Assert.Equal((int)Stage.Count, AnalyticsProf.Names.Length);
            Assert.Equal(AnalyticsProf.Names.Length, AnalyticsProf.Names.Distinct().Count());
            Assert.Equal((int)AnalyticsProf.Counter.Count, AnalyticsProf.CounterNames.Length);
            Assert.Equal("track.total", AnalyticsProf.Names[(int)Stage.TrackTotal]);
            Assert.Equal("v8.http", AnalyticsProf.Names[(int)Stage.V8Http]);
            Assert.Equal("pause.persist_now", AnalyticsProf.Names[(int)Stage.PersistNow]);
            Assert.Equal("jni.enqueue", AnalyticsProf.Names[(int)Stage.JniEnqueue]);
        }

        [Fact]
        public void StagesAccumulateCallsTimeAndTheLongestCall()
        {
            Assert.True(AnalyticsProf.Compiled);
            AnalyticsProf.Reset();
            for (var i = 0; i < 3; i++)
            {
                var t = AnalyticsProf.Begin();
                Thread.Sleep(i == 2 ? 30 : 5);
                AnalyticsProf.End(Stage.V1Ack, t);   // a stage no other test records, so parallel tests cannot disturb the numbers
            }
            AnalyticsProf.Count(AnalyticsProf.Counter.Retries, 3);
            AnalyticsProf.Count(AnalyticsProf.Counter.Connections, 1234);
            var lines = AnalyticsProf.Dump(false).Split('\n');
            var stage = lines.Single(l => l.StartsWith("S|v1.ack|")).Split('|');
            Assert.Equal("3", stage[2]);
            Assert.InRange(long.Parse(stage[3]), 35_000, 200_000);       // wall_us total: about 5 + 5 + 30 ms
            Assert.InRange(long.Parse(stage[6]), 25_000, 150_000);       // the longest call
            Assert.InRange(long.Parse(stage[8]), 4_000, 150_000);        // p99 index of three samples is the middle one
            Assert.Contains("C|retries|3", lines);
            Assert.Contains("C|connections|1234", lines);
        }

        [Fact]
        public void ResetForgetsEverythingAndTheTraceKeepsStartAndDuration()
        {
            AnalyticsProf.Reset();
            var t = AnalyticsProf.Begin();
            Thread.Sleep(10);
            AnalyticsProf.End(Stage.InitLifecycle, t);
            var trace = AnalyticsProf.Dump(true).Split('\n').Single(l => l.StartsWith("T|init.lifecycle|")).Split('|');
            Assert.InRange(long.Parse(trace[4]), 8_000, 100_000);        // duration in us
            AnalyticsProf.Reset();
            Assert.DoesNotContain("init.lifecycle", AnalyticsProf.Dump(true));
        }

        [Fact]
        public void TrackStagesAreNotTraced()
        {
            AnalyticsProf.Reset();
            var t = AnalyticsProf.Begin();
            AnalyticsProf.End(Stage.TrackLimiter, t);
            AnalyticsProf.End(Stage.JniOther, t);
            AnalyticsProf.End(Stage.WorkerPass, t);
            var text = AnalyticsProf.Dump(true);
            Assert.DoesNotContain("T|track.limiter", text);
            Assert.DoesNotContain("T|jni.other", text);
            Assert.Contains("T|worker.pass|", text);
            Assert.Contains("S|track.limiter|", text);
        }

        [Fact]
        public void TheJavaProfileIsAppendedWhenAProviderIsSet()
        {
            AnalyticsProf.Reset();
            AnalyticsProf.JavaProfile = () => "{\"enq.total\":[1,2,3,4,5]}";
            try { Assert.Contains("J|{\"enq.total\":[1,2,3,4,5]}", AnalyticsProf.Dump(false)); }
            finally { AnalyticsProf.JavaProfile = null; }
        }

        [Fact]
        public void TheProfiledBridgeForwardsCallsAndTimesThem()
        {
            AnalyticsProf.Reset();
            var inner = new FakeQueue();
            using (var bridge = new ProfiledQueueBridge(inner))
            {
                bridge.SetMeta("v8.token", "abc");
                Assert.Equal("abc", bridge.GetMeta("v8.token"));
                Assert.Equal(inner.PendingCount, bridge.PendingCount);
                bridge.GetState();
            }
            var text = AnalyticsProf.Dump(false);
            Assert.Contains("S|jni.meta|", text);
            Assert.Contains("S|jni.get_state|", text);
        }
    }
}
