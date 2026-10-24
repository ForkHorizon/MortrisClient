using System;
using System.Collections.Generic;
using System.Linq;
using Daliys.Analytics.Internal.Session;
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    public class SessionTrackerTests
    {
        private sealed class Sink : ISessionEventSink
        {
            internal readonly List<(string Name, Guid Session, long At, long Elapsed, Dictionary<string, object> Props)> Events = new List<(string, Guid, long, long, Dictionary<string, object>)>();
            public void Emit(string name, Guid sessionId, long at, long elapsed, IReadOnlyDictionary<string, object> properties) =>
                Events.Add((name, sessionId, at, elapsed, new Dictionary<string, object>((IDictionary<string, object>)properties)));
            internal string[] Names => Events.Select(e => e.Name).ToArray();
        }

        private sealed class Rig
        {
            internal long Now = 1_800_000_000_000;
            internal readonly Sink Sink = new Sink();
            internal readonly SessionTracker Tracker;
            private int _ids;
            internal Rig(TimeSpan? timeout = null) { Tracker = new SessionTracker(() => Now, timeout ?? TimeSpan.FromMinutes(5), Sink, () => new Guid(++_ids, 0, 0, new byte[8])); }
            internal void Advance(long ms) => Now += ms;
        }

        [Fact]
        public void StartBeginsASessionAndSaysSo()
        {
            var rig = new Rig();
            rig.Tracker.Start();
            Assert.Equal(new[] { SessionTracker.SessionStart }, rig.Sink.Names);
            Assert.Equal(true, rig.Sink.Events[0].Props["cold_start"]);
            Assert.Equal(rig.Now, rig.Tracker.Current.StartUnixMs);
        }

        [Fact]
        public void ABriefAbsenceKeepsTheSession()
        {
            var rig = new Rig(); rig.Tracker.Start(); var id = rig.Tracker.Current.Id;
            rig.Advance(60_000); rig.Tracker.OnPause(true);
            rig.Advance(20_000); rig.Tracker.OnPause(false);
            Assert.Equal(id, rig.Tracker.Current.Id);
            Assert.Equal(new[] { SessionTracker.SessionStart, SessionTracker.AppBackground, SessionTracker.AppForeground }, rig.Sink.Names);
            Assert.Equal(60_000L, rig.Sink.Events[1].Props["active_ms"]);
            Assert.Equal(20_000L, rig.Sink.Events[2].Props["paused_ms"]);
            Assert.Equal(false, rig.Sink.Events[2].Props["new_session"]);
        }

        [Fact]
        public void ALongAbsenceEndsTheSessionWhenThePlayerLeftAndStartsANewOne()
        {
            var rig = new Rig(TimeSpan.FromMinutes(5)); rig.Tracker.Start(); var first = rig.Tracker.Current;
            rig.Advance(90_000); rig.Tracker.OnPause(true); var left = rig.Now;
            rig.Advance(10 * 60_000); rig.Tracker.OnPause(false);
            Assert.NotEqual(first.Id, rig.Tracker.Current.Id);
            var end = rig.Sink.Events.Single(e => e.Name == SessionTracker.SessionEnd);
            Assert.Equal(first.Id, end.Session);
            Assert.Equal(left, end.At);                                  // ends when the player left, not when they came back
            Assert.Equal(90_000L, end.Props["duration_ms"]);
            Assert.Equal(90_000L, end.Props["active_ms"]);
            Assert.Equal("timeout", end.Props["reason"]);
            var starts = rig.Sink.Events.Where(e => e.Name == SessionTracker.SessionStart).ToList();
            Assert.Equal(2, starts.Count);
            Assert.Equal(false, starts[1].Props["cold_start"]);
            var foreground = rig.Sink.Events.Last(e => e.Name == SessionTracker.AppForeground);
            Assert.Equal(true, foreground.Props["new_session"]);
            Assert.Equal(rig.Tracker.Current.Id, foreground.Session);
        }

        [Fact]
        public void QuitEndsTheSessionNowOrWhenThePlayerLeft()
        {
            var rig = new Rig(); rig.Tracker.Start(); rig.Advance(30_000); rig.Tracker.OnQuit();
            var end = rig.Sink.Events.Single(e => e.Name == SessionTracker.SessionEnd);
            Assert.Equal(30_000L, end.Props["duration_ms"]); Assert.Equal("quit", end.Props["reason"]); Assert.Equal(false, end.Props["background"]);
            rig.Tracker.OnQuit();
            Assert.Single(rig.Sink.Events, e => e.Name == SessionTracker.SessionEnd); // once

            var other = new Rig(); other.Tracker.Start(); other.Advance(40_000); other.Tracker.OnPause(true); other.Advance(50_000); other.Tracker.OnQuit();
            var left = other.Sink.Events.Single(e => e.Name == SessionTracker.SessionEnd);
            Assert.Equal(40_000L, left.Props["duration_ms"]); Assert.Equal(true, left.Props["background"]);
        }

        [Fact]
        public void SnapshotChangesWithTheStateAndOnlyThen()
        {
            var rig = new Rig(); rig.Tracker.Start();
            var version = rig.Tracker.StateVersion; var snapshot = rig.Tracker.Snapshot();
            Assert.Equal(version, rig.Tracker.StateVersion);
            rig.Advance(5000); rig.Tracker.Touch();
            Assert.NotEqual(version, rig.Tracker.StateVersion);
            Assert.NotEqual(snapshot, rig.Tracker.Snapshot());
            Assert.Contains("\"ended\":0", rig.Tracker.Snapshot());
            rig.Tracker.OnQuit();
            Assert.Contains("\"ended\":1", rig.Tracker.Snapshot());
        }

        [Fact]
        public void APreviousProcessKilledInTheGameIsClosedAtTheKillTime()
        {
            var old = new Rig(); old.Tracker.Start(); old.Advance(100_000); old.Tracker.Touch();
            var saved = old.Tracker.Snapshot(); var oldId = old.Tracker.Current.Id; var start = old.Tracker.Current.StartUnixMs;
            var next = new Rig();
            var exit = "{\"reason\":5,\"status\":11,\"timestamp\":" + (start + 130_000) + ",\"importance\":100}";
            next.Tracker.Recover(saved, exit);
            var end = next.Sink.Events.Single();
            Assert.Equal(SessionTracker.SessionEnd, end.Name); Assert.Equal(oldId, end.Session);
            Assert.Equal(start + 130_000, end.At);
            Assert.Equal(130_000L, end.Props["duration_ms"]);
            Assert.Equal("native_crash", end.Props["reason"]); Assert.Equal(false, end.Props["background"]);
        }

        [Fact]
        public void APreviousProcessKilledInTheBackgroundEndedWhenThePlayerLeft()
        {
            var old = new Rig(); old.Tracker.Start(); old.Advance(70_000); old.Tracker.OnPause(true); var left = old.Now;
            var next = new Rig();
            next.Tracker.Recover(old.Tracker.Snapshot(), "{\"reason\":3,\"status\":0,\"timestamp\":" + (left + 3_600_000) + ",\"importance\":400}");
            var end = next.Sink.Events.Single();
            Assert.Equal(left, end.At); Assert.Equal(70_000L, end.Props["duration_ms"]); Assert.Equal("background_killed", end.Props["reason"]); Assert.Equal(true, end.Props["background"]);
        }

        [Fact]
        public void WithoutExitInformationTheLastProofOfLifeIsTheEnd()
        {
            var old = new Rig(); old.Tracker.Start(); old.Advance(25_000); old.Tracker.Touch(); var alive = old.Now;
            var next = new Rig(); next.Tracker.Recover(old.Tracker.Snapshot(), "");
            var end = next.Sink.Events.Single();
            Assert.Equal(alive, end.At); Assert.Equal("unknown_kill", end.Props["reason"]);
        }

        [Fact]
        public void AnExitRecordFromBeforeTheSessionIsIgnored()
        {
            var old = new Rig(); old.Tracker.Start(); old.Advance(25_000); old.Tracker.Touch();
            var next = new Rig();
            next.Tracker.Recover(old.Tracker.Snapshot(), "{\"reason\":4,\"timestamp\":" + (old.Tracker.Current.StartUnixMs - 1000) + "}");
            Assert.Equal("unknown_kill", next.Sink.Events.Single().Props["reason"]);
        }

        [Theory]
        [InlineData("")]
        [InlineData("not json")]
        [InlineData("{\"v\":1,\"id\":\"zzz\",\"ended\":0}")]
        public void NothingIsRecoveredFromMissingOrBrokenState(string state)
        {
            var rig = new Rig(); rig.Tracker.Recover(state, "");
            Assert.Empty(rig.Sink.Events);
        }

        [Fact]
        public void ACleanlyEndedPreviousSessionIsLeftAlone()
        {
            var old = new Rig(); old.Tracker.Start(); old.Tracker.OnQuit();
            var next = new Rig(); next.Tracker.Recover(old.Tracker.Snapshot(), "{\"reason\":4,\"timestamp\":" + (old.Now + 5) + "}");
            Assert.Empty(next.Sink.Events);
        }
    }

    public class EventBufferTests
    {
        private static byte[] Record(int size, byte fill) { var r = new byte[size]; for (var i = 0; i < size; i++) r[i] = fill; return r; }

        [Fact]
        public void DrainReturnsEverythingInOrderAsLengthPrefixedFrames()
        {
            var buffer = new EventBuffer(10, 1 << 20);
            Assert.True(buffer.TryAppend(Record(5, 1), 5)); Assert.True(buffer.TryAppend(Record(3, 2), 3));
            var frame = buffer.Drain(out var count);
            Assert.Equal(2, count); Assert.Equal(0, buffer.Count);
            Assert.Equal(new byte[] { 0, 0, 0, 5, 1, 1, 1, 1, 1, 0, 0, 0, 3, 2, 2, 2 }, frame);
            Assert.Empty(buffer.Drain(out count)); Assert.Equal(0, count);
        }

        [Fact]
        public void IsBoundedByCountAndBytesWithRoomForLifecycleEvents()
        {
            var buffer = new EventBuffer(2, 100);
            Assert.True(buffer.TryAppend(Record(10, 1), 10)); Assert.True(buffer.TryAppend(Record(10, 1), 10));
            Assert.False(buffer.TryAppend(Record(10, 1), 10));
            Assert.True(buffer.TryAppend(Record(10, 9), 10, priority: true));
            var small = new EventBuffer(100, 30);
            Assert.True(small.TryAppend(Record(20, 1), 20)); Assert.False(small.TryAppend(Record(20, 1), 20));
        }

        [Fact]
        public void RestoreReturnsRecordsInFrontOfNewerOnes()
        {
            var buffer = new EventBuffer(10, 1 << 20);
            buffer.TryAppend(Record(2, 1), 2);
            var frame = buffer.Drain(out var count);
            buffer.TryAppend(Record(2, 2), 2);
            buffer.Restore(frame, count);
            Assert.Equal(2, buffer.Count);
            Assert.Equal(new byte[] { 0, 0, 0, 2, 1, 1, 0, 0, 0, 2, 2, 2 }, buffer.Drain(out _));
        }

        [Fact]
        public void IsSafeUnderConcurrentWriters()
        {
            var buffer = new EventBuffer(100000, 1 << 26);
            var tasks = Enumerable.Range(0, 8).Select(t => System.Threading.Tasks.Task.Run(() => { for (var i = 0; i < 2000; i++) buffer.TryAppend(Record(40, (byte)t), 40); })).ToArray();
            System.Threading.Tasks.Task.WaitAll(tasks);
            Assert.Equal(16000, buffer.Count);
            var frame = buffer.Drain(out var count);
            Assert.Equal(16000, count); Assert.Equal(16000 * 44, frame.Length);
        }
    }
}
