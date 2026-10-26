using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    public class M8EncoderTests
    {
        private static readonly byte[] Context = EventContext.Build("1.1.14", "214", "android", "Android 15", "Pixel 8", "en-US", 60);
        private static readonly Guid[] Sessions = { Guid.Parse("7b1f3c52-9a44-4e0e-8d61-2f5c0a9e1b77"), Guid.Parse("7b1f3c52-9a44-4e0e-8d61-2f5c0a9e1b78") };
        private const long T0 = 1790000000000;

        /// <summary>An event to enqueue; the expected JSON is built from the same specification.</summary>
        private sealed class Spec { internal string Name; internal int Session; internal long ElapsedMs; internal Dictionary<string, object> Props = new Dictionary<string, object>(); }

        private static List<Spec> Mixed(int count)
        {
            var specs = new List<Spec>();
            for (var i = 0; i < count; i++)
            {
                var session = i < count / 2 ? 0 : 1;
                var s = new Spec { Session = session, ElapsedMs = i * 40 + 10 };
                switch (i % 5)
                {
                    case 0: s.Name = "level_end"; s.Props["coins"] = (long)(i % 17); s.Props["mode"] = i % 2 == 0 ? "hard" : "easy"; s.Props["score"] = (ulong)(900 + i); s.Props["time_s"] = 12.345679f + i; s.Props["won"] = i % 3 == 0; break;
                    case 1: s.Name = "position_sample"; s.Props["x"] = 0.1f * i; s.Props["y"] = -2.5f; s.Props["z"] = 0.25 * i; break;
                    case 2: s.Name = "ping"; break;
                    case 3: s.Name = "purchase"; s.Props["item"] = "deadbeef" + i.ToString("x8", CultureInfo.InvariantCulture); s.Props["run"] = Guid.NewGuid().ToString("D"); break;
                    default: s.Name = "speed_sample"; s.Props["speed"] = i % 2 == 0 ? 0f : 3f; s.Props["flag"] = (long)i; break; // a float that is sometimes 0 or integral: its shape must stay one
                }
                specs.Add(s);
            }
            return specs;
        }

        private static FakeQueue Fill(List<Spec> specs)
        {
            var queue = new FakeQueue();
            var writer = new EventRecordWriter { TypedNumbers = true };
            var frames = new List<byte>();
            for (var i = 0; i < specs.Count; i++)
            {
                var s = specs[i];
                writer.Begin(Guid.NewGuid(), Sessions[s.Session], T0 + i * 40, s.ElapsedMs, Context, s.Name, s.Props.Count);
                foreach (var p in s.Props) writer.AddClr(p.Key, p.Value);
                var length = writer.Finish();
                frames.AddRange(new[] { (byte)(length >> 24), (byte)(length >> 16), (byte)(length >> 8), (byte)length });
                frames.AddRange(writer.Buffer.Take(length));
            }
            queue.EnqueueRecords(frames.ToArray(), specs.Count, 1000000, 1L << 40, 1L << 40);
            return queue;
        }

        private static string Number(object v)
        {
            switch (v)
            {
                case float f: return f.ToString("R", CultureInfo.InvariantCulture);
                case double d: return d.ToString("R", CultureInfo.InvariantCulture);
                case ulong u: return u.ToString(CultureInfo.InvariantCulture);
                case long l: return l.ToString(CultureInfo.InvariantCulture);
                case bool b: return b ? "true" : "false";
                default: return MiniJson.Escape((string)v);
            }
        }

        private static string Expected(List<Spec> specs, int from, int count)
        {
            var json = new StringBuilder("[");
            for (var i = from; i < from + count; i++)
            {
                var s = specs[i];
                if (i > from) json.Append(',');
                json.Append("{\"sequence\":").Append(i + 1).Append(",\"name\":").Append(MiniJson.Escape(s.Name))
                    .Append(",\"time_ms\":").Append(T0 + i * 40).Append(",\"elapsed_ms\":").Append(s.ElapsedMs)
                    .Append(",\"session_id\":").Append(MiniJson.Escape(Sessions[s.Session].ToString("D")))
                    .Append(",\"app_version\":\"1.1.14\",\"build_number\":\"214\",\"platform\":\"android\",\"os_version\":\"Android 15\",\"device_class\":\"Pixel 8\",\"locale\":\"en-US\",\"timezone_offset_minutes\":60,\"properties\":{");
                json.Append(string.Join(",", s.Props.Select(p => MiniJson.Escape(p.Key) + ":" + Number(p.Value))));
                json.Append("}}");
            }
            return json.Append("]").ToString();
        }

        private static M8Encoder NewEncoder(M8Shapes shapes = null, M8Aliases aliases = null, bool compress = false) =>
            new M8Encoder(shapes ?? new M8Shapes(), aliases ?? new M8Aliases(), null, compress ? (IM7Compressor)new NativeZstdCompressor(null) : new NoCompressor(), "mortris-unity/0.2.0");

        private sealed class NoCompressor : IM7Compressor
        {
            public byte[] Compress(byte[] source, int length) => null;
            public void Dispose() { }
        }

        private static M8StreamInfo Info(long high, int serverShapes = 0, int serverAliases = 0, IReadOnlyList<KeyValuePair<long, long>> dropped = null) =>
            new M8StreamInfo { Epoch = 1, SentAtMs = T0 + 100000, StreamBase = 1, HighWater = high, ServerShapes = serverShapes, ServerAliases = serverAliases, Dropped = dropped };

        [Fact]
        public void TheFirstFrameCarriesAliasesAndShapesAndTheNextOneDoesNot()
        {
            var specs = Mixed(40);
            var queue = Fill(specs);
            var shapes = new M8Shapes(); var aliases = new M8Aliases();
            using (var encoder = NewEncoder(shapes, aliases))
            {
                var first = encoder.Encode(queue.SliceForTest(0, 20), Info(40));
                Assert.True(first.Ok, first.Failure);
                var f = first.Frame;
                Assert.Equal((byte)'M', f[0]); Assert.Equal((byte)'8', f[1]);
                Assert.Equal(8 | 16, f[2] & (8 | 16 | 32));    // aliases and shapes present, no dropped ranges
                Assert.Equal(M7FrameEncoder.Crc(f, f.Length - 4), BitConverter.ToUInt32(f, f.Length - 4));
                Assert.Equal(5, first.ShapeCount);
                Assert.Equal(1, first.AliasCount);              // 20 events in the first session
                var second = encoder.Encode(queue.SliceForTest(10, 10), Info(40, serverShapes: first.ShapeCount, serverAliases: first.AliasCount));
                Assert.True(second.Ok, second.Failure);
                Assert.Equal(0, second.Frame[2] & (8 | 16));   // the server holds everything the rows use
                Assert.Equal(5, second.ShapeCount);
                var third = encoder.Encode(queue.SliceForTest(20, 20), Info(40, serverShapes: 5, serverAliases: 1));
                Assert.Equal(2, third.AliasCount);              // the second session needs a new alias record
                Assert.Equal(8, third.Frame[2] & (8 | 16));
            }
        }

        [Fact]
        public void AFloatThatIsSometimesZeroKeepsOneShape()
        {
            var specs = Mixed(50);
            var queue = Fill(specs);
            var shapes = new M8Shapes();
            using (var encoder = NewEncoder(shapes))
            {
                Assert.True(encoder.Encode(queue.SliceForTest(0, 50), Info(50)).Ok);
                var speed = Enumerable.Range(0, shapes.Count).Select(i => shapes[i]).Where(s => s.Name == "speed_sample").ToList();
                Assert.Single(speed);
                Assert.Equal(new[] { 1, 3 }, new[] { speed[0].Kinds[0], speed[0].Kinds[1] }.OrderBy(x => x).Select((x, i) => i == 0 ? 1 : x).ToArray()); // flag int(0), speed float32(3): sorted keys flag, speed
                Assert.Equal(new[] { "flag", "speed" }, speed[0].Keys);
                Assert.Equal(new[] { M7Catalog.TypeInt, M7Catalog.TypeFloat32 }, speed[0].Kinds);
            }
        }

        [Fact]
        public void EncodingTheSameBatchTwiceIsDeterministicExceptForNothing()
        {
            var queue = Fill(Mixed(30));
            byte[] a, b;
            using (var e1 = NewEncoder()) a = e1.Encode(queue.SliceForTest(0, 30), Info(30)).Frame;
            using (var e2 = NewEncoder()) b = e2.Encode(queue.SliceForTest(0, 30), Info(30)).Frame;
            Assert.Equal(a, b);
        }

        [Fact]
        public void RejectsWhatTheServerWouldRefuse()
        {
            var queue = Fill(Mixed(10));
            using (var encoder = NewEncoder())
            {
                Assert.False(encoder.Encode(queue.SliceForTest(0, 10), Info(5)).Ok);                       // a row beyond high water
                Assert.False(encoder.Encode(queue.SliceForTest(0, 10), new M8StreamInfo { Epoch = 0, StreamBase = 1, HighWater = 10 }).Ok);
                Assert.False(encoder.Encode(QueueBatch.Empty, Info(10)).Ok);
            }
        }

        [Fact]
        public void ShapesRoundTripThroughTheCatalogDocument()
        {
            var queue = Fill(Mixed(30));
            var shapes = new M8Shapes();
            using (var encoder = NewEncoder(shapes)) Assert.True(encoder.Encode(queue.SliceForTest(0, 30), Info(30)).Ok);
            var json = shapes.ToJson("p");
            var loaded = new M8Shapes();
            Assert.True(loaded.TryLoad(json, "p"));
            Assert.Equal(shapes.Count, loaded.Count);
            Assert.Equal(json, loaded.ToJson("p"));
            Assert.Equal(shapes.CatalogId("p"), loaded.CatalogId("p"));
            Assert.False(new M8Shapes().TryLoad(json, "another"));
            Assert.False(new M8Shapes().TryLoad("{\"project_id\":\"p\",\"shapes\":[[\"Bad\",[]]]}", "p"));
            Assert.False(new M8Shapes().TryLoad("not json", "p"));
        }

        /// <summary>With M8_EXPORT_DIR set, writes C#-encoded frames and the events they carry so the server repository decodes them with its own Go decoder.</summary>
        [Fact]
        public void ExportsFramesForTheServerDecoderTests()
        {
            var dir = Environment.GetEnvironmentVariable("M8_EXPORT_DIR");
            if (string.IsNullOrEmpty(dir)) return;
            Directory.CreateDirectory(dir);
            var specs = Mixed(80);
            var queue = Fill(specs);
            var shapes = new M8Shapes(); var aliases = new M8Aliases();
            using (var encoder = NewEncoder(shapes, aliases, compress: true))
            {
                var one = encoder.Encode(queue.SliceForTest(0, 50), Info(80));
                Assert.True(one.Ok, one.Failure);
                File.WriteAllBytes(Path.Combine(dir, "frame-1.bin"), one.Frame);
                File.WriteAllText(Path.Combine(dir, "expected-1.json"), Expected(specs, 0, 50));
                var two = encoder.Encode(queue.SliceForTest(50, 20), Info(80, one.ShapeCount, one.AliasCount));
                Assert.True(two.Ok, two.Failure);
                File.WriteAllBytes(Path.Combine(dir, "frame-2.bin"), two.Frame);
                File.WriteAllText(Path.Combine(dir, "expected-2.json"), Expected(specs, 50, 20));
                var three = encoder.Encode(queue.SliceForTest(70, 10), Info(80, two.ShapeCount, two.AliasCount, new[] { new KeyValuePair<long, long>(1, 3) }));
                Assert.True(three.Ok, three.Failure);
                File.WriteAllBytes(Path.Combine(dir, "frame-3.bin"), three.Frame);
                File.WriteAllText(Path.Combine(dir, "expected-3.json"), Expected(specs, 70, 10));
            }
        }
    }
}
