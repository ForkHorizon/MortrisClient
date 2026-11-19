// Tests for the upload schedule and retry backoff.
using System;
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    public class UploadPacingTests
    {
        [Fact]
        public void WaitsDoubleUpToTheMaximumAndAreSpreadOverTheUpperHalf()
        {
            var low = new RetryBackoff(TimeSpan.FromSeconds(5), TimeSpan.FromMinutes(5), () => 0.0);
            var high = new RetryBackoff(TimeSpan.FromSeconds(5), TimeSpan.FromMinutes(5), () => 1.0);
            var steps = new[] { 5, 10, 20, 40, 80, 160, 300, 300 };
            foreach (var step in steps)
            {
                Assert.Equal(TimeSpan.FromSeconds(step / 2.0), low.OnFailure(null));
                Assert.Equal(TimeSpan.FromSeconds(step), high.OnFailure(null));
            }
        }

        [Fact]
        public void AFullV8PacketIsTheOptionNotTheV1Limit()
        {
            Assert.Equal(200, PacketSizer.FullPacket(500, 200, binaryTransport: true));   // V8 with the default MaxPacketEvents
            Assert.Equal(300, PacketSizer.FullPacket(300, 500, binaryTransport: true));   // the server's lower limit wins
            Assert.Equal(100, PacketSizer.FullPacket(500, 200, binaryTransport: false));  // V1 fallback
            Assert.Equal(50, PacketSizer.FullPacket(500, 50, binaryTransport: false));
        }

        [Fact]
        public void ResetStartsOver()
        {
            var b = new RetryBackoff(TimeSpan.FromSeconds(5), TimeSpan.FromMinutes(5), () => 1.0);
            b.OnFailure(null); b.OnFailure(null); b.OnFailure(null);
            b.Reset();
            Assert.Equal(TimeSpan.FromSeconds(5), b.OnFailure(null));
        }

        [Fact]
        public void RetryAfterIsHonoredNotEarlierNotBeyondTheCapAndDoesNotAdvanceTheSteps()
        {
            var b = new RetryBackoff(TimeSpan.FromSeconds(5), TimeSpan.FromMinutes(5), () => 0.0);
            Assert.Equal(TimeSpan.FromSeconds(42), b.OnFailure(TimeSpan.FromSeconds(42)));
            Assert.Equal(TimeSpan.FromSeconds(5) / 2, b.OnFailure(null));                           // the step is still the first one
            Assert.Equal(RetryBackoff.RetryAfterCap, b.OnFailure(TimeSpan.FromHours(3)));
            var withSpread = new RetryBackoff(TimeSpan.FromSeconds(5), TimeSpan.FromMinutes(5), () => 1.0).OnFailure(TimeSpan.FromSeconds(100));
            Assert.Equal(TimeSpan.FromSeconds(110), withSpread);
        }

        [Fact]
        public void PacketsShrinkAfterFailuresAndGrowBackAfterFastRequests()
        {
            var s = new PacketSizer(500);
            Assert.Equal(500, s.Next(500));
            s.OnFailure(); s.OnFailure();
            Assert.Equal(125, s.Next(500));
            s.OnSuccess(TimeSpan.FromMilliseconds(400), 500);
            Assert.Equal(187, s.Next(500));
            for (var i = 0; i < 10; i++) s.OnSuccess(TimeSpan.FromSeconds(1), 500);
            Assert.Equal(500, s.Next(500));
        }

        [Fact]
        public void ASlowSuccessTrimsTheSizeAndNeverGoesBelowTheMinimum()
        {
            var s = new PacketSizer(100);
            s.OnSuccess(TimeSpan.FromSeconds(9), 500);
            Assert.Equal(75, s.Next(500));
            for (var i = 0; i < 20; i++) s.OnFailure();
            Assert.Equal(PacketSizer.Minimum, s.Next(500));
            s.OnSuccess(TimeSpan.FromSeconds(5), 500);       // neither fast nor slow: unchanged
            Assert.Equal(PacketSizer.Minimum, s.Next(500));
        }

        [Fact]
        public void TheCeilingCanFallAndTheSizeFollowsIt()
        {
            var s = new PacketSizer(500);
            Assert.Equal(200, s.Next(200));
            Assert.Equal(200, s.Current);
        }
    }
}
