using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Globalization;
using Daliys.Analytics.Internal.Transport;

// Phase profile of the V7 encoder on real batches: replicates M7EventEncoder.Encode with timers around each step.
internal static class Profiler
{
    internal static string Run(string dir, string split, long maxEvents)
    {
        var catalog = M7Catalog.Parse(File.ReadAllBytes(Path.Combine(dir, "catalog.json"))); var dictionary = File.ReadAllBytes(Path.Combine(dir, "dictionary.bin"));
        double Ms(long ticks) => ticks * 1000.0 / Stopwatch.Frequency;
        long tParse = 0, tEvent = 0, tShape = 0, tRows = 0, tPack = 0, tCompress = 0, tGc = 0; long events = 0; long allocParse = 0, allocEvent = 0, allocShape = 0, allocRows = 0, allocPack = 0;
        string origin = null; M7Aliases aliases = null; M7FrameEncoder frames = null; TimedCompressor tc = null; int warm = 0;
        foreach (var line in File.ReadLines(Path.Combine(dir, "batches.jsonl")))
        {
            int s = line.IndexOf("\"split\":\"", StringComparison.Ordinal) + 9; if (split != "all" && line.Substring(s, 5) != split.Substring(0, 5)) continue;
            int o = line.IndexOf("\"origin\":\"", StringComparison.Ordinal) + 10; var org = line.Substring(o, line.IndexOf('"', o) - o);
            int ev = line.IndexOf("\"events\":", StringComparison.Ordinal) + 9; var text = line.Substring(ev, line.Length - ev - 1);
            if (org != origin) { origin = org; aliases = new M7Aliases(); tc = new TimedCompressor(new NativeZstdCompressor(dictionary)); frames = new M7FrameEncoder(tc, catalog.Id, aliases.Epoch, dictionary, true, true); }
            long a0 = GC.GetAllocatedBytesForCurrentThread(), t0 = Stopwatch.GetTimestamp();
            var raw = MiniJson.ParseArray(text);
            long a1 = GC.GetAllocatedBytesForCurrentThread(), t1 = Stopwatch.GetTimestamp();
            var parsed = new M7Event[raw.Count];
            for (var i = 0; i < raw.Count; i++) parsed[i] = M7Event.Parse((Dictionary<string, object>)raw[i], catalog.LogicalStrings);
            long a2 = GC.GetAllocatedBytesForCurrentThread(), t2 = Stopwatch.GetTimestamp();
            var rows = new M7Row[raw.Count]; var sessions = new Dictionary<string, int>(StringComparer.Ordinal); var fields = new List<KeyValuePair<string, int>>(); var shapes = new int[raw.Count]; var ctx = new int[raw.Count];
            bool ok = true;
            for (var i = 0; i < parsed.Length && ok; i++)
            {
                var e = parsed[i]; fields.Clear();
                foreach (var p in e.Properties) fields.Add(new KeyValuePair<string, int>(p.Key, p.Value.Type));
                shapes[i] = catalog.FindShape(e.Name, fields); if (shapes[i] < 0) { ok = false; break; }
                if (!aliases.TryRegister(origin, e, out ctx[i])) { ok = false; break; }
            }
            long a3 = GC.GetAllocatedBytesForCurrentThread(), t3 = Stopwatch.GetTimestamp();
            if (!ok) continue;
            for (var i = 0; i < parsed.Length; i++)
            {
                var e = parsed[i]; if (!sessions.TryGetValue(e.SessionId, out var session)) { session = sessions.Count; sessions.Add(e.SessionId, session); }
                var values = new M7Cell[e.Properties.Count];
                for (var j = 0; j < values.Length; j++) { var v = e.Properties[j].Value; values[j] = new M7Cell { I = v.I, U = v.U, D = v.D, S = v.S }; }
                rows[i] = new M7Row { Sequence = e.Sequence, Time = e.TimeMs, Elapsed = e.SessionElapsedMs, Shape = shapes[i], Context = ctx[i], Session = session, Columns = catalog.ShapeColumns[shapes[i]], Values = values };
            }
            long a4 = GC.GetAllocatedBytesForCurrentThread(), t4 = Stopwatch.GetTimestamp();
            long c0 = (long)TimedCompressor.Ns;
            frames.TryPack(rows, catalog.ColumnTypes, out var frame);
            long a5 = GC.GetAllocatedBytesForCurrentThread(), t5 = Stopwatch.GetTimestamp();
            if (warm++ < 100) continue;
            events += raw.Count;
            tParse += t1 - t0; tEvent += t2 - t1; tShape += t3 - t2; tRows += t4 - t3; var packTicks = t5 - t4; long comp = (long)TimedCompressor.Ns - c0; tCompress += (long)(comp * Stopwatch.Frequency / 1e9); tPack += packTicks;
            allocParse += a1 - a0; allocEvent += a2 - a1; allocShape += a3 - a2; allocRows += a4 - a3; allocPack += a5 - a4;
        }
        double n = Math.Max(events, 1); var ci = CultureInfo.InvariantCulture;
        double Ns(long ticks) => ticks * 1e9 / Stopwatch.Frequency / n;
        return "{\"events\":" + events + ",\"wall_ns_per_event\":{\"json_parse\":" + Ns(tParse).ToString("F0", ci) + ",\"event_parse_classify\":" + Ns(tEvent).ToString("F0", ci) + ",\"shape_and_alias\":" + Ns(tShape).ToString("F0", ci) +
            ",\"row_build\":" + Ns(tRows).ToString("F0", ci) + ",\"columns_pack_and_frame\":" + Ns(tPack - tCompress).ToString("F0", ci) + ",\"zstd_compress\":" + Ns(tCompress).ToString("F0", ci) + "}" +
            ",\"alloc_bytes_per_event\":{\"json_parse\":" + (allocParse / n).ToString("F0", ci) + ",\"event_parse_classify\":" + (allocEvent / n).ToString("F0", ci) + ",\"shape_and_alias\":" + (allocShape / n).ToString("F0", ci) +
            ",\"row_build\":" + (allocRows / n).ToString("F0", ci) + ",\"pack_compress_frame\":" + (allocPack / n).ToString("F0", ci) + "}}";
    }
}
