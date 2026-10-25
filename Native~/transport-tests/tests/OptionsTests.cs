using System;
using Daliys.Analytics;
using Xunit;

namespace M7Transport.Tests
{
    public class OptionsTests
    {
        private static AnalyticsOptions Valid() => new AnalyticsOptions { ServerUrl = "https://example.com", ProjectId = "p", Environment = "test" };

        [Fact]
        public void DefaultsFollowTheV8Schedule()
        {
            var o = Valid();
            o.Validate();
            Assert.Equal(TimeSpan.FromSeconds(120), o.UploadInterval);
            Assert.Equal(200, o.UploadEventThreshold);
            Assert.Equal(200, o.MaxPacketEvents);
            Assert.True(o.UploadOnBackground);
            Assert.Equal(TimeSpan.FromSeconds(30), o.BackgroundUploadMinGap);
            Assert.Equal(TimeSpan.FromSeconds(10), o.BackgroundUploadTimeout);
        }

        [Theory]
        [InlineData(0)]
        [InlineData(501)]
        [InlineData(-5)]
        public void PacketSizeOutsideTheFormatIsRejected(int size)
        {
            var o = Valid(); o.MaxPacketEvents = size;
            Assert.Throws<ArgumentOutOfRangeException>(() => o.Validate());
        }

        [Theory]
        [InlineData(1)]
        [InlineData(500)]
        public void PacketSizeLimitsAreAccepted(int size)
        {
            var o = Valid(); o.MaxPacketEvents = size;
            o.Validate();
        }

        [Fact]
        public void BackgroundAllowanceMustBePositive()
        {
            var o = Valid(); o.BackgroundUploadTimeout = TimeSpan.Zero;
            Assert.Throws<ArgumentOutOfRangeException>(() => o.Validate());
            o = Valid(); o.BackgroundUploadMinGap = TimeSpan.FromSeconds(-1);
            Assert.Throws<ArgumentOutOfRangeException>(() => o.Validate());
        }
    }
}
