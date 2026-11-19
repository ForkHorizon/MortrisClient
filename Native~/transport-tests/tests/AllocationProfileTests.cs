// Allocation and CPU per event for each stage of the event pipeline on a replay of real events.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using Daliys.Analytics.Internal;
using Daliys.Analytics.Internal.Transport;
using Xunit;
using Xunit.Abstractions;

namespace M7Transport.Tests
{
    /// <summary>
    /// Allocation and CPU per event for each stage of the new pipeline on real events (the 20k-event replay of the production export), measured on the host with
    /// GC.GetAllocatedBytesForCurrentThread. Skipped when the replay file is not present. The budgets are regression guards, deliberately loose; the printed
    /// numbers are what to read (dotnet test --logger "console;verbosity=detailed").
    /// </summary>
    public class AllocationProfileTests
    {
        private readonly ITestOutputHelper _out;
        public AllocationProfileTests(ITestOutputHelper output) { _out = output; }

        private static string Work(string name) => Path.GetFullPath(Path.Combine(TestSupport.Root, "../../../../../night-run~/work", name));

        private sealed class Event { internal string Name; internal Dictionary<string, object> Props; }

        private static List<Event> Load(int count)
        {
            var path = Work("replay_real_20k.jsonl");
            var events = new List<Event>();
            if (!File.Exists(path)) return events;
            foreach (var line in File.ReadLines(path))
            {
                if (events.Count >= count) break;
                var json = (Dictionary<string, object>)MiniJson.Parse(line);
                var props = new Dictionary<string, object>();
                foreach (var p in (Dictionary<string, object>)json["props"])
                {
                    switch (p.Value)
                    {
                        case JsonNumber n when n.Lexeme.IndexOfAny(new[] { '.', 'e', 'E' }) < 0: props[p.Key] = long.Parse(n.Lexeme, CultureInfo.InvariantCulture); break;
                        case JsonNumber n: props[p.Key] = double.Parse(n.Lexeme, CultureInfo.InvariantCulture); break;
                        default: props[p.Key] = p.Value; break;
                    }
                }
                events.Add(new Event { Name = (string)json["name"], Props = props });
            }
            return events;
        }

        private static (double bytesPerEvent, double microseconds) Measure(int events, Action work)
        {
            work(); // warm up (JIT, caches)
            GC.Collect(); GC.WaitForPendingFinalizers();
            var before = GC.GetAllocatedBytesForCurrentThread(); var watch = Stopwatch.StartNew();
            work();
            watch.Stop();
            return ((GC.GetAllocatedBytesForCurrentThread() - before) / (double)events, watch.Elapsed.TotalMilliseconds * 1000 / events);
        }

        [Fact]
        public void PerEventCostOfEveryStage()
        {
            var events = Load(5000);
            if (events.Count == 0) return;
            var context = EventContext.Build(120, "1.1.14", "perf-1", "android", "Android 16", "Nothing A142", "en-US");
            var session = Guid.NewGuid(); var writer = new EventRecordWriter();

            // Track(): validation + record. This is what the game thread pays.
            var validated = Measure(events.Count, () => { foreach (var e in events) EventValidator.HasValidProperties(e.Props); });
            var recorded = Measure(events.Count, () =>
            {
                foreach (var e in events)
                {
                    writer.Begin(new EventHeader(Guid.NewGuid(), session, 1790000000000, 1234, context), e.Name, e.Props.Count);
                    foreach (var p in e.Props) writer.AddClr(p.Key, p.Value);
                    writer.Finish();
                }
            });

            // the buffer and the queue wire format
            var buffer = new EventBuffer(100000, 1 << 28);
            var buffered = Measure(events.Count, () =>
            {
                foreach (var e in events)
                {
                    writer.Begin(new EventHeader(Guid.NewGuid(), session, 1790000000000, 1234, context), e.Name, e.Props.Count);
                    foreach (var p in e.Props) writer.AddClr(p.Key, p.Value);
                    buffer.TryAppend(writer.Buffer, writer.Finish());
                }
                buffer.Drain(out _);
            });

            // fill a queue stand-in with the same events and run the two consumers
            var queue = new FakeQueue();
            var frames = new List<byte>();
            foreach (var e in events)
            {
                writer.Begin(new EventHeader(Guid.NewGuid(), session, 1790000000000, 1234, context), e.Name, e.Props.Count);
                foreach (var p in e.Props) writer.AddClr(p.Key, p.Value);
                var length = writer.Finish();
                frames.AddRange(new[] { (byte)(length >> 24), (byte)(length >> 16), (byte)(length >> 8), (byte)length });
                frames.AddRange(writer.Buffer.Take(length));
            }
            queue.SetLimits(1000000, 1L << 40, 1L << 40); queue.EnqueueRecords(frames.ToArray(), events.Count);

            var catalog = M7Catalog.Parse(File.ReadAllBytes(Work("catalog.json")));
            var dictionary = File.ReadAllBytes(Work("dictionary.bin"));
            var encodedEvents = 0; var unknown = 0; string firstFailure = null;
            var slices = new List<QueueBatch>();
            for (var from = 0; from + 100 <= events.Count; from += 100) slices.Add(queue.SliceForTest(from, 100));
            var whole = queue.ReadOldest(100000);
            var encode = Measure(slices.Count * 100, () =>
            {
                encodedEvents = 0; unknown = 0;
                using (var encoder = new M7EventEncoder(catalog, new M7Aliases(), dictionary, Guid.NewGuid().ToString("D"), new NativeZstdCompressor(dictionary)))
                {
                    foreach (var slice in slices)
                    {
                        var result = encoder.Encode(slice);
                        if (result.Ok) encodedEvents += result.Count; else { unknown += 100; firstFailure = firstFailure ?? result.Failure; }
                    }
                }
            });
            var reader = new EventRecordReader();
            var json = Measure(whole.Count, () => whole.ToJsonArray(reader));
            var parsedOnly = new ParsedEvent();
            var parse = Measure(whole.Count, () => { for (var i = 0; i < whole.Count; i++) whole.Parse(reader, i, parsedOnly); });

            _out.WriteLine("per event (host .NET, real events, " + events.Count + " events, " + encodedEvents + " packed in V7 packets, " + unknown + " in batches the catalog could not encode)");
            _out.WriteLine("  first encode failure    : " + (firstFailure ?? "none"));
            _out.WriteLine("  validate                : {0,8:F0} B  {1,7:F2} us", validated.bytesPerEvent, validated.microseconds);
            _out.WriteLine("  record (Track body)     : {0,8:F0} B  {1,7:F2} us", recorded.bytesPerEvent, recorded.microseconds);
            _out.WriteLine("  record + buffer + drain : {0,8:F0} B  {1,7:F2} us", buffered.bytesPerEvent, buffered.microseconds);
            _out.WriteLine("  V7 encode (+read parse) : {0,8:F0} B  {1,7:F2} us", encode.bytesPerEvent, encode.microseconds);
            _out.WriteLine("  record parse only       : {0,8:F0} B  {1,7:F2} us", parse.bytesPerEvent, parse.microseconds);
            _out.WriteLine("  V1 json from records    : {0,8:F0} B  {1,7:F2} us", json.bytesPerEvent, json.microseconds);

            Assert.True(validated.bytesPerEvent < 600, "validator allocates " + validated.bytesPerEvent);
            Assert.True(recorded.bytesPerEvent < 600, "record writer allocates " + recorded.bytesPerEvent);
        }
    }
}
