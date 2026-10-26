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
    
        [Fact]
        public void QueueDefaultsBoundOnlyTheBytesAndKeepEventsForever()
        {
            var o = Valid(); o.Validate();
            Assert.Equal(0, o.DurableEventLimit);                     // no limit by count
            Assert.Equal(64L * 1024 * 1024, o.DurableByteLimit);
            Assert.Equal(TimeSpan.Zero, o.MaxEventAge);               // events never expire
            Assert.Equal(2 * 1024 * 1024, o.EventBufferBytes);
            Assert.Equal(500, o.BacklogPacketEvents);
            Assert.True(o.AdaptivePacketSize);
        }

        [Fact]
        public void NegativeQueueLimitsAreRejectedAndZeroMeansNone()
        {
            var o = Valid(); o.DurableEventLimit = 0; o.MaxEventAge = TimeSpan.Zero; o.Validate();
            o = Valid(); o.DurableEventLimit = -1;
            Assert.Throws<ArgumentOutOfRangeException>(() => o.Validate());
            o = Valid(); o.MaxEventAge = TimeSpan.FromSeconds(-1);
            Assert.Throws<ArgumentOutOfRangeException>(() => o.Validate());
            o = Valid(); o.DurableByteLimit = 0;
            Assert.Throws<ArgumentOutOfRangeException>(() => o.Validate());
        }

        [Theory]
        [InlineData(0)]
        [InlineData(501)]
        public void BacklogPacketSizeOutsideTheFormatIsRejected(int size)
        {
            var o = Valid(); o.BacklogPacketEvents = size;
            Assert.Throws<ArgumentOutOfRangeException>(() => o.Validate());
        }

        [Theory]
        [InlineData(1024)]
        [InlineData(128 * 1024 * 1024)]
        public void EventBufferSizeOutsideTheRangeIsRejected(int bytes)
        {
            var o = Valid(); o.EventBufferBytes = bytes;
            Assert.Throws<ArgumentOutOfRangeException>(() => o.Validate());
        }

        [Fact]
        public void ProfilesSetTheThreeUploadKnobs()
        {
            var realtime = Valid().UseProfile(AnalyticsProfile.Realtime); realtime.Validate();
            Assert.Equal(TimeSpan.FromSeconds(5), realtime.UploadInterval); Assert.Equal(20, realtime.UploadEventThreshold); Assert.Equal(200, realtime.MaxPacketEvents);
            var saver = Valid().UseProfile(AnalyticsProfile.TrafficSaver); saver.Validate();
            Assert.Equal(TimeSpan.FromMinutes(5), saver.UploadInterval); Assert.Equal(500, saver.UploadEventThreshold); Assert.Equal(500, saver.MaxPacketEvents);
            var standard = Valid().UseProfile(AnalyticsProfile.Realtime).UseProfile(AnalyticsProfile.Standard);
            Assert.Equal(TimeSpan.FromSeconds(120), standard.UploadInterval); Assert.Equal(200, standard.UploadEventThreshold); Assert.Equal(200, standard.MaxPacketEvents);
        }
}
}
