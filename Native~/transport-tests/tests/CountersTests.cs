using System;
using Daliys.Analytics.Internal;
using Xunit;

namespace M7Transport.Tests
{
    public class CountersTests
    {
        [Fact]
        public void CountersStartAtOneAndNeverGoBack()
        {
            var c = new AnalyticsCounters();
            c.Load("");
            Assert.Equal(1, c.Next("attempt"));
            Assert.Equal(2, c.Next("attempt"));
            Assert.Equal(1, c.Next("house_run"));
            Assert.Equal(3, c.Next("attempt"));
        }

        [Fact]
        public void StoredValuesContinueAndAreSnapshottedOnlyWhenTheyChange()
        {
            var c = new AnalyticsCounters();
            c.Load("{\"attempt\":41,\"house_run\":7}");
            Assert.Null(c.Snapshot());
            Assert.Equal(42, c.Next("attempt"));
            var snapshot = c.Snapshot();
            Assert.Contains("\"attempt\":42", snapshot);
            Assert.Contains("\"house_run\":7", snapshot);
            Assert.Null(c.Snapshot());                       // nothing new since
            c.MarkDirty();                                   // the write failed: offer it again
            Assert.NotNull(c.Snapshot());
        }

        [Fact]
        public void ANumberHandedOutBeforeTheLoadIsNotReused()
        {
            var c = new AnalyticsCounters();
            Assert.Equal(1, c.Next("a"));
            c.Load("{\"a\":0,\"b\":5}");                     // the stored value is behind what this process already issued
            Assert.Equal(2, c.Next("a"));
            Assert.Equal(6, c.Next("b"));
        }

        [Fact]
        public void DamagedStorageIsIgnoredAndBadNamesRefused()
        {
            var c = new AnalyticsCounters();
            c.Load("{not json");
            Assert.True(c.IsLoaded);
            Assert.Equal(1, c.Next("x"));
            foreach (var bad in new[] { "", "Upper", "a-b", new string('a', 65), null })
                Assert.Throws<ArgumentException>(() => c.Next(bad));
            var c2 = new AnalyticsCounters();
            for (var i = 0; i < AnalyticsCounters.MaxCounters; i++) c2.Next("n" + i);
            Assert.Throws<InvalidOperationException>(() => c2.Next("one_too_many"));
            Assert.Equal(2, c2.Next("n0"));                  // existing counters keep working at the limit
        }

        [Fact]
        public void NegativeAndNonNumericStoredValuesAreIgnored()
        {
            var c = new AnalyticsCounters();
            c.Load("{\"a\":-5,\"b\":\"x\",\"c\":3}");
            Assert.Equal(1, c.Next("a"));
            Assert.Equal(1, c.Next("b"));
            Assert.Equal(4, c.Next("c"));
        }
    }
}
