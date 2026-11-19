// V8 end-to-end tests: the C# session against the real Go server with real zstd and a trained dictionary.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net.Http;
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    /// <summary>
    /// V8 end to end: the C# session talks HTTP to the Go server (MortrisServer branch feat/v8-transport) on a throwaway PostgreSQL, with the real native zstd.
    /// Run through e2e/run-e2e.sh with MORTRIS_SERVER_REPO pointing at the V8 server; without M7_E2E_URL these tests do nothing.
    /// </summary>
    public class E2EV8Tests
    {
        private static readonly byte[] Context = EventContext.Build(60, "1.1.14", "214", "android", "Android 15", "Pixel 8", "en-US");

        private sealed class Rig : IDisposable
        {
            internal readonly string Url = Environment.GetEnvironmentVariable("M7_E2E_URL");
            internal readonly string Project = "v8e2e_" + Guid.NewGuid().ToString("N").Substring(0, 12);
            internal readonly HttpClient Client = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false, AutomaticDecompression = System.Net.DecompressionMethods.GZip });
            internal readonly FakeQueue Queue = new FakeQueue();
            internal readonly IV7AssetStore Store = new MemoryV7AssetStore();
            internal readonly IV7Http Http;
            internal V8Session Session;
            internal Guid SessionId = Guid.NewGuid();
            internal long SentBytes;
            private int _written;

            internal Rig(Func<IV7Http, IV7Http> wrap = null)
            {
                Sql("INSERT INTO projects (id, environment, display_name, strict_catalog, enabled) VALUES ('" + Project + "', 'test', '" + Project + "', false, true)");
                var plain = new HttpV7Transport(Client, Url);
                Http = new Counting(wrap != null ? wrap(plain) : plain, this);
                NewProcess();
            }

            internal void NewProcess()
            {
                Session?.Dispose();
                SessionId = Guid.NewGuid();
                Session = new V8Session(new V8Settings { ProjectId = Project, SdkName = "mortris-unity", SdkVersion = "0.2.0", AppVersion = "1.1.14", BuildNumber = "214", Platform = "android" }, Http, Store);
            }

            private sealed class Counting : IV7Http
            {
                private readonly IV7Http _inner; private readonly Rig _rig;
                internal Counting(IV7Http inner, Rig rig) { _inner = inner; _rig = rig; }
                public V7Response PostJson(string p, string j, string c) => _inner.PostJson(p, j, c);
                public V7Response PutJson(string p, string j, string c) => _inner.PutJson(p, j, c);
                public V7Response PostPacket(string p, byte[] b, IReadOnlyDictionary<string, string> h, string c) => _inner.PostPacket(p, b, h, c);
                public V7Response PostBinary(string p, byte[] b, string t, string c) { _rig.SentBytes += b.Length; return _inner.PostBinary(p, b, t, c); }
                public V7Response Get(string p, string c) => _inner.Get(p, c);
            }

            internal void Enqueue(int count, Func<int, (string name, Dictionary<string, object> props)> make)
            {
                var writer = new EventRecordWriter { TypedNumbers = true };
                var frames = new List<byte>();
                for (var i = 0; i < count; i++, _written++)
                {
                    var (name, props) = make(_written);
                    writer.Begin(new EventHeader(Guid.NewGuid(), SessionId, DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() - 1000 + i, 10 + _written * 3, Context), name, props.Count);
                    foreach (var p in props) writer.AddClr(p.Key, p.Value);
                    var length = writer.Finish();
                    frames.AddRange(new[] { (byte)(length >> 24), (byte)(length >> 16), (byte)(length >> 8), (byte)length });
                    frames.AddRange(writer.Buffer.Take(length));
                }
                Queue.SetLimits(1000000, 1L << 40, 1L << 40); Queue.EnqueueRecords(frames.ToArray(), count);
            }

            internal V7SendResult Send(int max = 100) => Session.Send(Queue, () => Queue.ReadOldest(max));

            internal List<V7SendResult> Drain(int max = 100, int guard = 100)
            {
                var results = new List<V7SendResult>();
                for (var i = 0; i < guard && Queue.Pending > 0; i++)
                {
                    var r = Send(max);
                    results.Add(r);
                    if (r.Kind != V7ResultKind.Delivered) break;
                }
                return results;
            }

            internal string Sql(string sql)
            {
                var file = Path.GetTempFileName();
                File.WriteAllText(file, sql);
                try
                {
                    var start = new ProcessStartInfo("/bin/sh", "-c \"" + Environment.GetEnvironmentVariable("M7_E2E_PSQL") + " -f " + file + "\"") { RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false };
                    using (var process = Process.Start(start))
                    {
                        var output = process.StandardOutput.ReadToEnd();
                        var error = process.StandardError.ReadToEnd();
                        process.WaitForExit();
                        Assert.True(process.ExitCode == 0, error);
                        return output.Trim();
                    }
                }
                finally { File.Delete(file); }
            }

            internal long Count(string where = "true") => long.Parse(Sql("SELECT COUNT(*) FROM events WHERE project_id = '" + Project + "' AND " + where));
            public void Dispose() { Session?.Dispose(); Client.Dispose(); }
        }

        private static bool Skip()
        {
            if (!string.IsNullOrEmpty(Environment.GetEnvironmentVariable("M7_E2E_URL"))) return false;
            Assert.True(Environment.GetEnvironmentVariable("M7_E2E_REQUIRED") != "1", "M7_E2E_REQUIRED=1 but M7_E2E_URL is not set");
            return true;
        }

        private static (string, Dictionary<string, object>) Level(int i) => i % 3 == 0
            ? ("level_end", new Dictionary<string, object> { ["coins"] = (long)(i % 50), ["mode"] = i % 2 == 0 ? "hard" : "easy", ["time_s"] = 12.345679f + i % 7, ["won"] = i % 4 == 0 })
            : i % 3 == 1 ? ("position_sample", new Dictionary<string, object> { ["x"] = 0.1f * (i % 100), ["y"] = -2.5f, ["z"] = 0.25 * (i % 9) })
            : ("speed_sample", new Dictionary<string, object> { ["speed"] = i % 2 == 0 ? 0f : 3f, ["flag"] = (long)i });

        /// <summary>Diagnostic: pushes the first M8_CORPUS_N events of a JSONL corpus ({"name","props"}) through the session and prints what every send returned. Skipped without M8_CORPUS.</summary>
        [Fact]
        public void ZCorpusFromFile()
        {
            var file = Environment.GetEnvironmentVariable("M8_CORPUS");
            if (Skip() || string.IsNullOrEmpty(file)) return;
            var limit = int.Parse(Environment.GetEnvironmentVariable("M8_CORPUS_N") ?? "2000");
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
                    events.Add((doc.RootElement.GetProperty("name").GetString(), props));
                }
            }
            using (var rig = new Rig())
            {
                rig.Enqueue(events.Count, i => events[i]);
                var log = new List<string>();
                for (var guard = 0; guard < 200 && rig.Queue.Pending > 0; guard++)
                {
                    var r = rig.Send(100);
                    log.Add(r.Kind + " status=" + r.Status + " pending=" + rig.Queue.Pending);
                    if (r.Kind != V7ResultKind.Delivered && r.Kind != V7ResultKind.Empty) { if (log.Count > 30) break; }
                }
                Console.WriteLine("CORPUS sent=" + events.Count + " db=" + rig.Count() + " pending=" + rig.Queue.Pending + "\n" + string.Join("\n", log.Take(40)));
            }
        }

        [Fact]
        public void ARegistrationAndTwoHundredFiftyEventsOverRealHttp()
        {
            if (Skip()) return;
            using (var rig = new Rig())
            {
                rig.Enqueue(250, Level);
                var results = rig.Drain();
                Assert.All(results, r => Assert.Equal(V7ResultKind.Delivered, r.Kind));
                Assert.Equal(0, rig.Queue.Pending);
                Assert.Equal(250, rig.Count());
                Assert.Equal("3", rig.Sql("SELECT COUNT(*) FROM transport_shapes WHERE project_id = '" + rig.Project + "'"));
                // values survive: a float32, an integral float32, a double, a bool, strings
                Assert.Equal("12.345679", rig.Sql("SELECT properties->>'time_s' FROM events WHERE project_id = '" + rig.Project + "' AND name = 'level_end' AND sequence = 1"));
                Assert.Equal("0", rig.Sql("SELECT properties->>'speed' FROM events WHERE project_id = '" + rig.Project + "' AND name = 'speed_sample' AND sequence = 3"));
                Assert.Equal("3", rig.Sql("SELECT properties->>'speed' FROM events WHERE project_id = '" + rig.Project + "' AND name = 'speed_sample' AND sequence = 6"));
                Assert.Equal("0.1", rig.Sql("SELECT properties->>'x' FROM events WHERE project_id = '" + rig.Project + "' AND name = 'position_sample' AND sequence = 2").Replace("0.10000000149011612", "0.1"));
                Assert.Equal("1", rig.Sql("SELECT COUNT(DISTINCT install_id) FROM events WHERE project_id = '" + rig.Project + "'"));
                Assert.Equal("1", rig.Sql("SELECT COUNT(*) FROM transport_installs WHERE project_id = '" + rig.Project + "'"));
                Assert.Equal("1", rig.Sql("SELECT COUNT(*) FROM transport_streams WHERE project_id = '" + rig.Project + "' AND epoch = 1"));
            }
        }

        [Fact]
        public void ASecondProcessContinuesTheStreamWithoutHello()
        {
            if (Skip()) return;
            using (var rig = new Rig())
            {
                rig.Enqueue(40, Level);
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                var token = rig.Session.Token;
                rig.NewProcess();
                rig.Enqueue(40, Level);
                var result = rig.Send();
                Assert.Equal(V7ResultKind.Delivered, result.Kind);
                Assert.Equal(token, rig.Session.Token);
                Assert.Equal(80, rig.Count());
                Assert.Equal("1", rig.Sql("SELECT COUNT(*) FROM transport_installs WHERE project_id = '" + rig.Project + "'"));
                Assert.Equal("2", rig.Sql("SELECT COUNT(DISTINCT session_id) FROM events WHERE project_id = '" + rig.Project + "'"));
            }
        }

        [Fact]
        public void ABigPacketIsAcceptedAndANewShapeRegisters()
        {
            if (Skip()) return;
            using (var rig = new Rig())
            {
                rig.Enqueue(450, Level);
                Assert.Equal(V7ResultKind.Delivered, rig.Send(450).Kind);          // 450 events in one frame; the server stores them in chunks of 100
                Assert.Equal(450, rig.Count());
                rig.Enqueue(20, i => ("fresh_event", new Dictionary<string, object> { ["a"] = (long)i, ["b"] = "text" }));
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.Equal("4", rig.Sql("SELECT COUNT(*) FROM transport_shapes WHERE project_id = '" + rig.Project + "'"));
                Assert.Equal(470, rig.Count());
            }
        }

        private sealed class LosesFirstAck : IV7Http
        {
            private readonly IV7Http _inner; private bool _lost;
            internal LosesFirstAck(IV7Http inner) { _inner = inner; }
            public V7Response PostJson(string p, string j, string c) => _inner.PostJson(p, j, c);
            public V7Response PutJson(string p, string j, string c) => _inner.PutJson(p, j, c);
            public V7Response PostPacket(string p, byte[] b, IReadOnlyDictionary<string, string> h, string c) => _inner.PostPacket(p, b, h, c);
            public V7Response Get(string p, string c) => _inner.Get(p, c);
            public V7Response PostBinary(string p, byte[] b, string t, string c)
            {
                var real = _inner.PostBinary(p, b, t, c);
                if (_lost) return real;
                _lost = true;
                return new V7Response(503, new byte[0], null);
            }
        }

        [Fact]
        public void ALostAcknowledgementStoresNothingTwice()
        {
            if (Skip()) return;
            using (var rig = new Rig(inner => new LosesFirstAck(inner)))
            {
                rig.Enqueue(60, Level);
                Assert.Equal(V7ResultKind.Retry, rig.Send().Kind);
                Assert.Equal(60, rig.Queue.Pending);
                Assert.Equal(60, rig.Count());                    // the server has them
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.Equal(0, rig.Queue.Pending);
                Assert.Equal(60, rig.Count());
            }
        }

        [Fact]
        public void ALostTokenKeyAndALostStreamRecover()
        {
            if (Skip()) return;
            using (var rig = new Rig())
            {
                rig.Enqueue(30, Level);
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                rig.Sql("DELETE FROM transport_streams WHERE project_id = '" + rig.Project + "'");          // the server lost the stream
                rig.Enqueue(30, Level);
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.Equal(60, rig.Count());
                Assert.Equal("1", rig.Sql("SELECT COUNT(*) FROM transport_streams WHERE project_id = '" + rig.Project + "'"));
            }
        }

        [Fact]
        public void RealPuzzleEventsThroughV8AndTheTrainedDictionary()
        {
            if (Skip()) return;
            var path = Path.GetFullPath(Path.Combine(TestSupport.Root, "../../../../../night-run~/work/replay_real_20k.jsonl"));
            if (!File.Exists(path)) return;
            var events = new List<KeyValuePair<string, Dictionary<string, object>>>();
            foreach (var line in File.ReadLines(path).Take(5000))
            {
                var json = (Dictionary<string, object>)MiniJson.Parse(line);
                var props = new Dictionary<string, object>();
                foreach (var p in (Dictionary<string, object>)json["props"])
                    switch (p.Value)
                    {
                        case JsonNumber n when n.Lexeme.IndexOfAny(new[] { '.', 'e', 'E' }) < 0: props[p.Key] = long.Parse(n.Lexeme, CultureInfo.InvariantCulture); break;
                        case JsonNumber n: props[p.Key] = double.Parse(n.Lexeme, CultureInfo.InvariantCulture); break;
                        default: props[p.Key] = p.Value; break;
                    }
                events.Add(new KeyValuePair<string, Dictionary<string, object>>((string)json["name"], props));
            }
            using (var rig = new Rig())
            {
                rig.Enqueue(events.Count, i => (events[i].Key, events[i].Value));
                var results = rig.Drain(200);
                Assert.All(results, r => Assert.Equal(V7ResultKind.Delivered, r.Kind));
                Assert.Equal(events.Count, rig.Count());
                Console.WriteLine("V8 e2e: {0} real events in {1} packets, {2} bytes of packets = {3:F1} B/event (the server trained a dictionary after 2000 events)", events.Count, results.Count, rig.SentBytes, rig.SentBytes / (double)events.Count);
                // the answer to the next packet announces the dictionary the server trained; the packet after it is compressed with it and the server decodes it
                var dictionaries = int.Parse(rig.Sql("SELECT COUNT(*) FROM transport_assets WHERE project_id = '" + rig.Project + "' AND kind = 'dictionary'"));
                Assert.Equal(1, dictionaries);
                rig.NewProcess();
                rig.Enqueue(400, i => (events[i % events.Count].Key, events[i % events.Count].Value));
                var before = rig.SentBytes;
                Assert.Equal(V7ResultKind.Delivered, rig.Send(200).Kind);
                var withoutDictionary = rig.SentBytes - before;
                before = rig.SentBytes;
                Assert.Equal(V7ResultKind.Delivered, rig.Send(200).Kind);
                var withDictionary = rig.SentBytes - before;
                Console.WriteLine("V8 e2e: 200 events {0} bytes without the dictionary, {1} bytes with it", withoutDictionary, withDictionary);
                Assert.Equal(events.Count + 400, rig.Count());
            }
        }

        private static List<KeyValuePair<string, Dictionary<string, object>>> LoadReplay(int count, bool v8Content)
        {
            var path = Path.GetFullPath(Path.Combine(TestSupport.Root, "../../../../../night-run~/work/replay_real_20k.jsonl"));
            var events = new List<KeyValuePair<string, Dictionary<string, object>>>();
            if (!File.Exists(path)) return events;
            var numbers = new Dictionary<string, Dictionary<string, long>> { ["attempt_id"] = new Dictionary<string, long>(), ["house_run_id"] = new Dictionary<string, long>() };
            foreach (var line in File.ReadLines(path).Take(count))
            {
                var json = (Dictionary<string, object>)MiniJson.Parse(line);
                var props = new Dictionary<string, object>();
                foreach (var p in (Dictionary<string, object>)json["props"])
                {
                    if (v8Content && (p.Key == "wave_attempt_id" || p.Key == "interaction_id" || p.Key == "placed_state_hash")) continue;   // decisions D9 and D10
                    if (v8Content && numbers.TryGetValue(p.Key, out var map)) { var text = (string)p.Value; if (!map.TryGetValue(text, out var n)) map[text] = n = map.Count + 1; props[p.Key] = n; continue; }
                    switch (p.Value)
                    {
                        case JsonNumber n when n.Lexeme.IndexOfAny(new[] { '.', 'e', 'E' }) < 0: props[p.Key] = long.Parse(n.Lexeme, CultureInfo.InvariantCulture); break;
                        case JsonNumber n: props[p.Key] = double.Parse(n.Lexeme, CultureInfo.InvariantCulture); break;
                        default: props[p.Key] = p.Value; break;
                    }
                }
                events.Add(new KeyValuePair<string, Dictionary<string, object>>((string)json["name"], props));
            }
            return events;
        }

        [Fact]
        public void TheDecidedEventContentCostsAboutNineBytesOnTheWire()
        {
            if (Skip()) return;
            var events = LoadReplay(6000, v8Content: true);
            if (events.Count == 0) return;
            using (var rig = new Rig())
            {
                rig.Enqueue(events.Count, i => (events[i % events.Count].Key, events[i % events.Count].Value));
                var results = rig.Drain(500);                    // 500-event packets: the server limits requests per installation, not events
                Assert.All(results, r => Assert.Equal(V7ResultKind.Delivered, r.Kind));
                Assert.Equal(events.Count, rig.Count());
                var perEventBefore = rig.SentBytes / (double)events.Count;
                // the server trained a dictionary from the first packets; the next packets announce and then use it
                rig.NewProcess();
                rig.Enqueue(800, i => (events[i % events.Count].Key, events[i % events.Count].Value));
                Assert.Equal(V7ResultKind.Delivered, rig.Send(200).Kind);
                var mark = rig.SentBytes;
                var delivered = 0;
                for (var i = 0; i < 3; i++) { Assert.Equal(V7ResultKind.Delivered, rig.Send(200).Kind); delivered += 200; }
                var perEventWith = (rig.SentBytes - mark) / (double)delivered;
                Console.WriteLine("V8 e2e decided content: {0:F2} B/event over {1} events in 500-event packets while the dictionary was being trained; {2:F2} B/event with the trained dictionary", perEventBefore, events.Count, perEventWith);
                Assert.True(perEventWith < 14, "with a dictionary the decided content should be far below the 20 B of the old content: " + perEventWith);
                Assert.Equal(events.Count + 800, rig.Count());
            }
        }
    }
}
