// Host allocation and CPU per event for the managed stages of the V8 path.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using Daliys.Analytics.Internal;
using Daliys.Analytics.Internal.Transport;
using Xunit;
using Xunit.Abstractions;

namespace M7Transport.Tests
{
    /// <summary>
    /// Host-side (.NET) allocation and CPU per event for the managed stages of the V8 path, exact because GC.GetAllocatedBytesForCurrentThread works here (it returns 0 under
    /// IL2CPP). Reads every *.jsonl ({"name","props"}) of the directory in M8_CORPUS_DIR (comparison-run~/data) and prints one table per corpus; does nothing without it.
    /// dotnet test --filter V8StageAllocation --logger "console;verbosity=detailed"
    /// </summary>
    public class V8StageAllocationTests
    {
        private readonly ITestOutputHelper _out;
        public V8StageAllocationTests(ITestOutputHelper output) { _out = output; }

        private static readonly byte[] Context = EventContext.Build(60, "1.1.14", "214", "android", "Android 15", "Pixel 8", "en-US");

        private static List<(string Name, Dictionary<string, object> Props)> Load(string file, int limit)
        {
            var events = new List<(string, Dictionary<string, object>)>();
            foreach (var line in File.ReadLines(file))
            {
                if (events.Count >= limit) break;
                using (var doc = System.Text.Json.JsonDocument.Parse(line))
                {
                    var props = new Dictionary<string, object>();
                    foreach (var kv in doc.RootElement.GetProperty("props").EnumerateObject())
                        props[kv.Name] = kv.Value.ValueKind == System.Text.Json.JsonValueKind.String ? kv.Value.GetString()
                            : kv.Value.ValueKind == System.Text.Json.JsonValueKind.True ? true : kv.Value.ValueKind == System.Text.Json.JsonValueKind.False ? false
                            : kv.Value.TryGetInt64(out var l) ? (object)l : kv.Value.GetDouble();
                    if (props.Count <= 32) events.Add((doc.RootElement.GetProperty("name").GetString(), props));
                }
            }
            return events;
        }

        private static (double bytes, double micros) Measure(int events, Action work)
        {
            work();
            GC.Collect(); GC.WaitForPendingFinalizers();
            var before = GC.GetAllocatedBytesForCurrentThread(); var watch = Stopwatch.StartNew();
            work();
            watch.Stop();
            return ((GC.GetAllocatedBytesForCurrentThread() - before) / (double)events, watch.Elapsed.TotalMilliseconds * 1000 / events);
        }

        private sealed class NoCompressor : IM7Compressor { public byte[] Compress(byte[] source, int length) => null; public void Dispose() { } }

        [Fact]
        public void PerEventCostOfTheManagedStagesOfV8()
        {
            var dir = Environment.GetEnvironmentVariable("M8_CORPUS_DIR");
            if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) return;
            foreach (var file in Directory.GetFiles(dir, "*_slice_00.jsonl").OrderBy(f => f))
            {
                var events = Load(file, 3000);
                if (events.Count < 400) continue;
                var session = Guid.NewGuid(); var writer = new EventRecordWriter { TypedNumbers = true };
                var validated = Measure(events.Count, () => { foreach (var e in events) EventValidator.HasValidProperties(e.Props); });
                var recorded = Measure(events.Count, () => { foreach (var e in events) { writer.Begin(new EventHeader(Guid.NewGuid(), session, 1790000000000, 1234, Context), e.Name, e.Props.Count); foreach (var p in e.Props) writer.AddClr(p.Key, p.Value); writer.Finish(); } });
                var buffer = new EventBuffer(1 << 30, 64 * 1024 * 1024);
                var buffered = Measure(events.Count, () =>
                {
                    foreach (var e in events) { writer.Begin(new EventHeader(Guid.NewGuid(), session, 1790000000000, 1234, Context), e.Name, e.Props.Count); foreach (var p in e.Props) writer.AddClr(p.Key, p.Value); buffer.TryAppend(writer.Buffer, writer.Finish()); }
                    buffer.Drain(out _);
                });
                var queue = new FakeQueue(); var frames = new List<byte>();
                foreach (var e in events)
                {
                    writer.Begin(new EventHeader(Guid.NewGuid(), session, 1790000000000, 1234, Context), e.Name, e.Props.Count);
                    foreach (var p in e.Props) writer.AddClr(p.Key, p.Value);
                    var length = writer.Finish();
                    frames.AddRange(new[] { (byte)(length >> 24), (byte)(length >> 16), (byte)(length >> 8), (byte)length }); frames.AddRange(writer.Buffer.Take(length));
                }
                queue.SetLimits(1000000, 1L << 40, 1L << 40); queue.EnqueueRecords(frames.ToArray(), events.Count);
                var shapes = new M8Shapes(); var aliases = new M8Aliases();
                foreach (var size in new[] { 20, 200, 500 })
                {
                    var slices = new List<QueueBatch>();
                    for (var from = 0; from + size <= events.Count; from += size) slices.Add(queue.SliceForTest(from, size));
                    var n = slices.Count * size;
                    long frameBytes = 0;
                    var info = new M8StreamInfo { Epoch = 1, SentAtMs = 1790000100000, StreamBase = 1, HighWater = events.Count };
                    using (var encoder = new M8Encoder(shapes, aliases, null, new NativeZstdCompressor(null), "mortris-unity/0.2.0"))
                    {
                        foreach (var s in slices) { var r = encoder.Encode(s, new M8StreamInfo { Epoch = 1, SentAtMs = info.SentAtMs, StreamBase = 1, HighWater = events.Count, ServerShapes = shapes.Count, ServerAliases = aliases.Count }); if (r.Ok) frameBytes += r.Frame.Length; }
                        frameBytes = 0;
                        var encode = Measure(n, () => { frameBytes = 0; foreach (var s in slices) { var r = encoder.Encode(s, new M8StreamInfo { Epoch = 1, SentAtMs = info.SentAtMs, StreamBase = 1, HighWater = events.Count, ServerShapes = shapes.Count, ServerAliases = aliases.Count }); if (r.Ok) frameBytes += r.Frame.Length; } });
                        _out.WriteLine("{0,-26} packet {1,3}: validate {2,6:F0} B {3,5:F2} us | record {4,6:F0} B {5,5:F2} us | +buffer+drain {6,6:F0} B {7,5:F2} us | V8 encode {8,6:F0} B {9,6:F2} us | frame {10,5:F1} B/event | shapes {11}",
                            Path.GetFileName(file), size, validated.bytes, validated.micros, recorded.bytes, recorded.micros, buffered.bytes, buffered.micros, encode.bytes, encode.micros, frameBytes / (double)n, shapes.Count);
                    }
                }
            }
        }
    }
}
