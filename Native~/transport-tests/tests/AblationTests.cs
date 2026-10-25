using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using Daliys.Analytics.Internal;
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    /// <summary>
    /// Byte cost of event fields with the real encoder: for every variant directory under $M7_ABLATION (see tools/make_ablation.py) it encodes the variant's
    /// events in batches of 100 and writes frame bytes per event, with and without the project dictionary, to $M7_ABLATION/results.csv. Skipped when unset.
    /// </summary>
    public class AblationTests
    {
        [Fact]
        public void FrameBytesPerEventForEveryVariant()
        {
            var root = Environment.GetEnvironmentVariable("M7_ABLATION");
            if (string.IsNullOrEmpty(root)) return;
            var dictionary = File.ReadAllBytes(Path.GetFullPath(Path.Combine(TestSupport.Root, "../../../../../night-run~/work/dictionary.bin")));
            var context = EventContext.Build("1.1.14", "perf-1", "android", "Android 16", "Nothing A142", "en-US", 120);
            var session = Guid.Parse("7b1f3c52-9a44-4e0e-8d61-2f5c0a9e1b77");
            var results = new StringBuilder("variant,events,frames_failed,frame_bytes_per_event_dict,frame_bytes_per_event_nodict,raw_columns_per_event\n");
            foreach (var name in File.ReadAllLines(Path.Combine(root, "manifest.txt")).Where(l => l.Length > 0))
            {
                var dir = Path.Combine(root, name);
                var catalog = M7Catalog.Parse(File.ReadAllBytes(Path.Combine(dir, "catalog.json")));
                var events = new List<(string name, Dictionary<string, object> props, long ts, long el)>();
                foreach (var line in File.ReadLines(Path.Combine(dir, "events.jsonl")).Where(l => l.Length > 0))
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
                    events.Add(((string)json["name"], props, json.TryGetValue("ts", out var tsv) ? long.Parse(((JsonNumber)tsv).Lexeme, CultureInfo.InvariantCulture) : -1, json.TryGetValue("el", out var elv) ? long.Parse(((JsonNumber)elv).Lexeme, CultureInfo.InvariantCulture) : -1));
                }
                long withDict = 0, noDict = 0, raw = 0; var count = 0; var failed = 0;
                foreach (var useDict in new[] { true, false })
                {
                    var d = useDict ? dictionary : null;
                    var writer = new EventRecordWriter();
                    using (var encoder = new M7EventEncoder(catalog, new M7Aliases(), d, "0d9e6c8e-1d0b-4c1e-9d8a-3f7a2b6c4e11", new NativeZstdCompressor(d)))
                    {
                        for (var from = 0; from + 100 <= events.Count; from += 100)
                        {
                            var frames = new List<byte>(); long t = 1790000000000;
                            for (var i = from; i < from + 100; i++)
                            {
                                var e = events[i];
                                writer.Begin(Guid.NewGuid(), session, e.ts >= 0 ? e.ts : t + (i - from) * 40, e.el >= 0 ? e.el : 1234 + (i - from) * 40, context, e.name, e.props.Count);
                                foreach (var p in e.props) writer.AddClr(p.Key, p.Value);
                                var len = writer.Finish();
                                frames.AddRange(new[] { (byte)(len >> 24), (byte)(len >> 16), (byte)(len >> 8), (byte)len }); frames.AddRange(writer.Buffer.Take(len));
                            }
                            var queue = new FakeQueue(); queue.EnqueueRecords(frames.ToArray(), 100, 1000000, 1L << 40, 1L << 40);
                            var r = encoder.Encode(queue.ReadOldest(100000));
                            if (!r.Ok) { if (useDict) failed++; continue; }
                            if (useDict) { withDict += r.Frame.Length; count += 100; int p2 = 28; ReadVar(r.Frame, ref p2); raw += ReadVar(r.Frame, ref p2); }
                            else noDict += r.Frame.Length;
                        }
                    }
                }
                results.AppendLine(string.Format(CultureInfo.InvariantCulture, "{0},{1},{2},{3:F3},{4:F3},{5:F3}", name, count, failed, withDict / (double)Math.Max(1, count), noDict / (double)Math.Max(1, count), raw / (double)Math.Max(1, count)));
            }
            File.WriteAllText(Path.Combine(root, "results.csv"), results.ToString());
        }

        private static int ReadVar(byte[] b, ref int p) { int r = 0, s = 0; while (true) { var x = b[p++]; r |= (x & 127) << s; if (x < 128) return r; s += 7; } }
    }
}
