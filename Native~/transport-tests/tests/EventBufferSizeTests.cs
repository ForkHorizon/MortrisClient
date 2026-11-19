// Tests for the memory buffer size limits between Track() and the queue.
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    public class EventBufferSizeTests
    {
        [Fact]
        public void ABurstDoesNotLeaveTheBufferArrayGrownAfterItWasDrained()
        {
            var buffer = new EventBuffer(1 << 30, 2 * 1024 * 1024);
            var record = new byte[1000];
            for (var i = 0; i < 1500; i++) Assert.True(buffer.TryAppend(record, record.Length));     // 1.5 MB: the array grew well past 256 KB
            var frame = buffer.Drain(out var count);
            Assert.Equal(1500, count);
            Assert.Equal(1500 * 1004, frame.Length);
            for (var i = 0; i < 3; i++) Assert.True(buffer.TryAppend(record, record.Length));      // still works after the shrink
            Assert.Equal(3, buffer.Count);
            Assert.Equal(3 * 1004, buffer.Drain(out _).Length);
        }

        [Fact]
        public void TheBufferIsBoundedByBytesAndRefusesTheRecordThatDoesNotFit()
        {
            var buffer = new EventBuffer(1 << 30, 10 * 1004);
            var record = new byte[1000];
            for (var i = 0; i < 10; i++) Assert.True(buffer.TryAppend(record, record.Length));
            Assert.False(buffer.TryAppend(record, record.Length));
            buffer.Drain(out _);
            Assert.True(buffer.TryAppend(record, record.Length));
        }
    }
}
