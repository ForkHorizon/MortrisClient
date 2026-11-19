// Tests for the per-name event rate limiter.
using Daliys.Analytics.Internal;
using Xunit;

namespace M7Transport.Tests
{
    public class RateLimiterTests
    {
        private long _now;
        private EventRateLimiter Make(int perSecond) => new EventRateLimiter(perSecond, () => _now, 1000); // 1000 ticks per second

        [Fact]
        public void NoLimitMeansEverythingPasses()
        {
            var limiter = Make(0);
            for (var i = 0; i < 10000; i++) Assert.True(limiter.TryAcquire("move"));
            Assert.Equal(0, limiter.Limited);
        }

        [Fact]
        public void BurstUpToTheLimitThenRefusedUntilTimePasses()
        {
            var limiter = Make(5);
            for (var i = 0; i < 5; i++) Assert.True(limiter.TryAcquire("tap"));
            Assert.False(limiter.TryAcquire("tap"));
            Assert.Equal(1, limiter.Limited);
            _now += 200; // 0.2 s = one token at 5 per second
            Assert.True(limiter.TryAcquire("tap"));
            Assert.False(limiter.TryAcquire("tap"));
        }

        [Fact]
        public void NamesHaveSeparateBuckets()
        {
            var limiter = Make(1);
            Assert.True(limiter.TryAcquire("a"));
            Assert.False(limiter.TryAcquire("a"));
            Assert.True(limiter.TryAcquire("b"));
        }

        [Fact]
        public void TokensDoNotPileUpBeyondTheBurst()
        {
            var limiter = Make(3);
            _now += 3_600_000; // an hour idle
            for (var i = 0; i < 3; i++) Assert.True(limiter.TryAcquire("x"));
            Assert.False(limiter.TryAcquire("x"));
        }

        [Fact]
        public void PerNameLimitsOverrideAndCanExempt()
        {
            var limiter = Make(1);
            limiter.SetLimit("noisy", 2);
            Assert.True(limiter.TryAcquire("noisy")); Assert.True(limiter.TryAcquire("noisy")); Assert.False(limiter.TryAcquire("noisy"));
            limiter.SetLimit("free", -1);
            for (var i = 0; i < 50; i++) Assert.True(limiter.TryAcquire("free"));
            limiter.SetLimit("noisy", 0); // back to the default of 1
            Assert.True(limiter.TryAcquire("noisy")); Assert.False(limiter.TryAcquire("noisy"));
        }

        [Fact]
        public void LimitFromAnOtherwiseUnlimitedConfigurationWorks()
        {
            var limiter = Make(0);
            limiter.SetLimit("only", 1);
            Assert.True(limiter.TryAcquire("only")); Assert.False(limiter.TryAcquire("only"));
            Assert.True(limiter.TryAcquire("other"));
        }

        [Fact]
        public void TheDefaultCanBeReplacedAtRunTime()
        {
            var limiter = Make(0);
            limiter.SetDefault(1);
            Assert.True(limiter.TryAcquire("e")); Assert.False(limiter.TryAcquire("e"));
            limiter.SetDefault(0);
            for (var i = 0; i < 20; i++) Assert.True(limiter.TryAcquire("e"));
        }
    }
}
