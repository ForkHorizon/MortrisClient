// Field cost ablation: encodes each variant corpus with the real encoder and reports bytes per event.
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
        private static readonly byte[] Context = EventContext.Build(120, "1.1.14", "perf-1", "android", "Android 16", "Nothing A142", "en-US");
        private static readonly Guid Session = Guid.Parse("7b1f3c52-9a44-4e0e-8d61-2f5c0a9e1b77");

        private struct AblationEvent
        {
            internal string Name;
            internal Dictionary<string, object> Props;
            internal long Ts, El;
        }

        /// <summary>One variant's corpus and what encoding it produced.</summary>
        private sealed class Variant
        {
            internal string Name, Root, FirstFailure = "";
            internal M7Catalog Catalog;
            internal List<AblationEvent> Events;
            internal int Count, Failed;
            internal long WithDict, NoDict, Raw;
        }

        [Fact]
        public void FrameBytesPerEventForEveryVariant()
        {
            var root = Environment.GetEnvironmentVariable("M7_ABLATION"); var batch = int.TryParse(Environment.GetEnvironmentVariable("M7_BATCH"), out var bsz) ? bsz : 100;
            if (string.IsNullOrEmpty(root)) return;
            var dictionary = File.ReadAllBytes(Path.GetFullPath(Path.Combine(TestSupport.Root, "../../../../../night-run~/work/dictionary.bin")));
            var results = new StringBuilder("variant,events,frames_failed,frame_bytes_per_event_dict,frame_bytes_per_event_nodict,raw_columns_per_event,first_failure\n");
            foreach (var name in File.ReadAllLines(Path.Combine(root, "manifest.txt")).Where(l => l.Length > 0))
            {
                var dir = Path.Combine(root, name);
                var variant = new Variant { Name = name, Root = root, Catalog = M7Catalog.Parse(File.ReadAllBytes(Path.Combine(dir, "catalog.json"))), Events = LoadEvents(Path.Combine(dir, "events.jsonl")) };
                Encode(variant, dictionary, batch, true);
                Encode(variant, null, batch, false);
                results.AppendLine(string.Format(CultureInfo.InvariantCulture, "{0},{1},{2},{3:F3},{4:F3},{5:F3},{6}", name, variant.Count, variant.Failed,
                    variant.WithDict / (double)Math.Max(1, variant.Count), variant.NoDict / (double)Math.Max(1, variant.Count), variant.Raw / (double)Math.Max(1, variant.Count), variant.FirstFailure.Replace(',', ';')));
            }
            File.WriteAllText(Path.Combine(root, "results.csv"), results.ToString());
        }

        private static List<AblationEvent> LoadEvents(string path)
        {
            var events = new List<AblationEvent>();
            foreach (var line in File.ReadLines(path).Where(l => l.Length > 0))
            {
                var json = (Dictionary<string, object>)MiniJson.Parse(line);
                var props = new Dictionary<string, object>();
                foreach (var p in (Dictionary<string, object>)json["props"]) props[p.Key] = ToClr(p.Value);
                events.Add(new AblationEvent { Name = (string)json["name"], Props = props, Ts = OptionalLong(json, "ts"), El = OptionalLong(json, "el") });
            }
            return events;
        }

        private static object ToClr(object value)
        {
            if (!(value is JsonNumber n)) return value;
            return n.Lexeme.IndexOfAny(new[] { '.', 'e', 'E' }) < 0 ? (object)long.Parse(n.Lexeme, CultureInfo.InvariantCulture) : double.Parse(n.Lexeme, CultureInfo.InvariantCulture);
        }

        private static long OptionalLong(Dictionary<string, object> json, string key) =>
            json.TryGetValue(key, out var v) ? long.Parse(((JsonNumber)v).Lexeme, CultureInfo.InvariantCulture) : -1;

        private static void Encode(Variant variant, byte[] dictionary, int batch, bool useDict)
        {
            var writer = new EventRecordWriter();
            using (var encoder = new M7EventEncoder(variant.Catalog, new M7Aliases(), dictionary, "0d9e6c8e-1d0b-4c1e-9d8a-3f7a2b6c4e11", new NativeZstdCompressor(dictionary)))
            {
                for (var from = 0; from + batch <= variant.Events.Count; from += batch)
                {
                    var queue = new FakeQueue(); queue.SetLimits(1000000, 1L << 40, 1L << 40); queue.EnqueueRecords(Frames(writer, variant.Events, from, batch), batch);
                    var r = encoder.Encode(queue.ReadOldest(100000));
                    if (!r.Ok) { if (useDict) OnFailure(variant, queue, r.Failure); continue; }
                    if (useDict) { variant.WithDict += r.Frame.Length; variant.Count += batch; int p2 = 28; ReadVar(r.Frame, ref p2); variant.Raw += ReadVar(r.Frame, ref p2); }
                    else { variant.NoDict += r.Frame.Length; Dump(variant.Name, from, r.Frame); }
                }
            }
        }

        private static byte[] Frames(EventRecordWriter writer, List<AblationEvent> events, int from, int batch)
        {
            var frames = new List<byte>(); long t = 1790000000000;
            for (var i = from; i < from + batch; i++)
            {
                var e = events[i];
                writer.Begin(new EventHeader(Guid.NewGuid(), Session, e.Ts >= 0 ? e.Ts : t + (i - from) * 40, e.El >= 0 ? e.El : 1234 + (i - from) * 40, Context), e.Name, e.Props.Count);
                foreach (var p in e.Props) writer.AddClr(p.Key, p.Value);
                var len = writer.Finish();
                frames.AddRange(new[] { (byte)(len >> 24), (byte)(len >> 16), (byte)(len >> 8), (byte)len }); frames.AddRange(writer.Buffer.Take(len));
            }
            return frames.ToArray();
        }

        private static void OnFailure(Variant variant, FakeQueue queue, string failure)
        {
            variant.Failed++;
            if (variant.FirstFailure.Length > 0) return;
            variant.FirstFailure = failure;
            if (Environment.GetEnvironmentVariable("M7_DEBUG") != null) DebugFirstUnknownShape(variant, queue);
        }

        /// <summary>M7_DEBUG: appends the first event of the batch whose typed key set the catalog does not know to debug.txt.</summary>
        private static void DebugFirstUnknownShape(Variant variant, FakeQueue queue)
        {
            var batchRead = queue.ReadOldest(100000); var reader = new EventRecordReader(); var parsed = new ParsedEvent();
            for (var bi = 0; bi < batchRead.Count; bi++)
            {
                batchRead.Parse(reader, bi, parsed); var me = M7Event.FromParsed(parsed, bi + 1, variant.Catalog.LogicalStrings);
                var fl = me.Properties.Select(pp => new KeyValuePair<string, int>(pp.Key, pp.Value.Type)).ToList();
                if (variant.Catalog.FindShape(me.Name, fl) >= 0) continue;
                File.AppendAllText(Path.Combine(variant.Root, "debug.txt"), variant.Name + " " + me.Name + " " + string.Join(",", fl.Select(f => f.Key + ":" + f.Value)) + "\n");
                return;
            }
        }

        private static void Dump(string name, int from, byte[] frame)
        {
            var dump = Environment.GetEnvironmentVariable("M7_DUMP");
            if (string.IsNullOrEmpty(dump)) return;
            var vd = Path.Combine(dump, name); Directory.CreateDirectory(vd); File.WriteAllBytes(Path.Combine(vd, from.ToString("D8") + ".bin"), frame);
        }

        private static int ReadVar(byte[] b, ref int p) { int r = 0, s = 0; while (true) { var x = b[p++]; r |= (x & 127) << s; if (x < 128) return r; s += 7; } }
    }
}
