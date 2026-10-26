using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Text;
using Daliys.Analytics.Internal.Transport;

// Host benchmark of the real V7 encoder (and the V1 gzip path) on real events.
// Metrics per 100-event batch: wire bytes, thread CPU ns, wall ns, managed allocated bytes. A fixed calibration spin runs between
// chunks so contention from other processes can be separated from the code under test.
internal sealed class TimedCompressor : IM7Compressor
{
    private readonly IM7Compressor _inner; internal static ulong Ns; internal static long In, Out, Calls;
    internal TimedCompressor(IM7Compressor inner) { _inner = inner; }
    public byte[] Compress(byte[] source, int length)
    {
        var t0 = System.Diagnostics.Stopwatch.GetTimestamp(); var r = _inner.Compress(source, length); Ns += (ulong)((System.Diagnostics.Stopwatch.GetTimestamp() - t0) * 1e9 / System.Diagnostics.Stopwatch.Frequency);
        In += length; Out += r?.Length ?? 0; Calls++; return r;
    }
    public void Dispose() => _inner.Dispose();
}

internal static class Program
{
    [DllImport("libc")] private static extern ulong clock_gettime_nsec_np(int clock);
    private static ulong ThreadCpuNs() => clock_gettime_nsec_np(16); // CLOCK_THREAD_CPUTIME_ID on macOS

    static double Calibrate()
    {
        // fixed mixed workload: integer mixing + a 4 MB working set, repeated; returns ns per iteration (thread CPU)
        var buf = new int[1 << 20];
        var t0 = ThreadCpuNs(); ulong acc = 1469598103934665603UL;
        for (int r = 0; r < 12; r++)
            for (int i = 0; i < buf.Length; i += 7) { acc = (acc ^ (ulong)buf[(i * 31 + r) & (buf.Length - 1)]) * 1099511628211UL; buf[(i * 17) & (buf.Length - 1)] += (int)acc; }
        var t1 = ThreadCpuNs(); if (acc == 42) Console.Write(""); return (t1 - t0) / (12.0 * (buf.Length / 7));
    }

    static string Q(string s) => "\"" + s + "\"";

    static int Main(string[] args)
    {
        System.Globalization.CultureInfo.DefaultThreadCurrentCulture = System.Globalization.CultureInfo.InvariantCulture; System.Globalization.CultureInfo.CurrentCulture = System.Globalization.CultureInfo.InvariantCulture;
        NativeLibrary.SetDllImportResolver(typeof(NativeZstdCompressor).Assembly, (name, asm, p) => name != "daliys_zstd" ? IntPtr.Zero :
            NativeLibrary.Load(Environment.GetEnvironmentVariable("DALIYS_ZSTD")));
        if (args[0] == "memory")
        {
            var cat = M7Catalog.Parse(File.ReadAllBytes(Path.Combine(args[1], "catalog.json"))); var dic = File.ReadAllBytes(Path.Combine(args[1], "dictionary.bin"));
            var mbatches = new List<string>(); string org = null;
            foreach (var line in File.ReadLines(Path.Combine(args[1], "batches.jsonl")))
            {
                if (!line.Contains("\"split\":\"holdout\"")) continue;
                int o = line.IndexOf("\"origin\":\"", StringComparison.Ordinal) + 10; var oo = line.Substring(o, line.IndexOf('"', o) - o); if (org == null) org = oo; if (oo != org) break;
                int ev = line.IndexOf("\"events\":", StringComparison.Ordinal) + 9; mbatches.Add(line.Substring(ev, line.Length - ev - 1));
            }
            GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); long m0 = GC.GetTotalMemory(true); long r0 = Process.GetCurrentProcess().WorkingSet64;
            var al = new M7Aliases(); var enc = new M7EventEncoder(cat, al, dic, org, new NativeZstdCompressor(dic));
            GC.Collect(); long m1 = GC.GetTotalMemory(true); long r1 = Process.GetCurrentProcess().WorkingSet64; var ci2 = System.Globalization.CultureInfo.InvariantCulture; var steps = new List<string>();
            int n = 0; foreach (var b in mbatches) { enc.Encode(b); n++; if (n == 1 || n == 10 || n == 50 || n == mbatches.Count) { GC.Collect(); steps.Add("{\"batches\":" + n + ",\"alias_records\":" + al.Count + ",\"managed_retained_kb\":" + ((GC.GetTotalMemory(true) - m1) / 1024.0).ToString("F1", ci2) + "}"); } }
            GC.Collect(); long m2 = GC.GetTotalMemory(true); long r2 = Process.GetCurrentProcess().WorkingSet64;
            Console.WriteLine("{\"install_batches\":" + mbatches.Count + ",\"managed_baseline_kb\":" + (m0 / 1024) + ",\"encoder_created_managed_kb\":" + ((m1 - m0) / 1024.0).ToString("F1", ci2) + ",\"encoder_created_rss_kb\":" + ((r1 - r0) / 1024) + ",\"after_encoding_managed_kb\":" + ((m2 - m0) / 1024.0).ToString("F1", ci2) + ",\"after_encoding_rss_delta_kb\":" + ((r2 - r0) / 1024) + ",\"alias_records\":" + al.Count + ",\"steps\":[" + string.Join(",", steps) + "],\"catalog_bytes\":" + File.ReadAllBytes(Path.Combine(args[1], "catalog.json")).Length + ",\"dictionary_bytes\":" + dic.Length + "}");
            return 0;
        }
        if (args[0] == "profile") { Console.WriteLine(Profiler.Run(args[1], args[2], long.MaxValue)); return 0; }
        string dir = args[0], label = args[1]; string split = args.Length > 2 ? args[2] : "holdout"; long maxEvents = args.Length > 3 ? long.Parse(args[3]) : long.MaxValue;
        string outFile = args.Length > 4 ? args[4] : null; string packets = args.Length > 5 ? args[5] : null;
        var catalog = M7Catalog.Parse(File.ReadAllBytes(Path.Combine(dir, "catalog.json")));
        var dictionary = File.ReadAllBytes(Path.Combine(dir, "dictionary.bin"));
        var proc = Process.GetCurrentProcess();
        // warm up JIT on the first 200 batches (not counted)
        var rssStart = 0L;
        var lines = new List<string>(); var origins = new List<string>(); var counts = new List<int>();
        double calBest = double.MaxValue; var calRows = new List<string>();
        long events = 0, v7Bytes = 0, v1Bytes = 0, fallback = 0, batches = 0, v7Ok = 0;
        ulong v7Cpu = 0, v7Wall = 0, parseCpu = 0, v1Cpu = 0; long v7Alloc = 0, v1Alloc = 0, parseAlloc = 0;
        var perBatchCpu = new List<double>(); var perBatchAlloc = new List<double>(); var perBatchBytes = new List<double>();
        var perBatchCpuCorr = new List<double>();
        int gc0 = GC.CollectionCount(0), gc1 = GC.CollectionCount(1), gc2 = GC.CollectionCount(2);
        var failures = new Dictionary<string, int>(); M7EventEncoder encoder = null; string currentOrigin = null; M7Aliases currentAliases = null; StreamWriter aliasOut = packets != null ? new StreamWriter(packets + ".aliases.jsonl") : null;
        using (var packetStream = packets != null ? new BinaryWriter(File.Create(packets)) : null)
        using (var reader = new StreamReader(Path.Combine(dir, "batches.jsonl")))
        {
            int ChunkBatches = int.Parse(Environment.GetEnvironmentVariable("CHUNK") ?? "300");
            bool done = false; int warm = 0;
            while (!done)
            {
                lines.Clear(); origins.Clear(); counts.Clear();
                string line;
                while (lines.Count < ChunkBatches && (line = reader.ReadLine()) != null)
                {
                    int s = line.IndexOf("\"split\":\"", StringComparison.Ordinal) + 9; int se = line.IndexOf('"', s);
                    if (split != "all" && line.Substring(s, se - s) != split) continue;
                    int o = line.IndexOf("\"origin\":\"", StringComparison.Ordinal) + 10; int oe = line.IndexOf('"', o);
                    int ev = line.IndexOf("\"events\":", StringComparison.Ordinal) + 9;
                    origins.Add(line.Substring(o, oe - o)); lines.Add(line.Substring(ev, line.Length - ev - 1));
                    int n = 0; for (int i = 0; i < lines[lines.Count - 1].Length; i++) if (lines[lines.Count - 1][i] == '{' && i + 12 < lines[lines.Count - 1].Length && string.CompareOrdinal(lines[lines.Count - 1], i, "{\"event_id\"", 0, 11) == 0) n++;
                    counts.Add(n);
                }
                if (lines.Count == 0) break;
                if (maxEvents != long.MaxValue && events >= maxEvents) break;
                var cal = Calibrate(); if (cal < calBest) calBest = cal;
                var chunkCpu0 = v7Cpu; long chunkEvents0 = events;
                for (int b = 0; b < lines.Count; b++)
                {
                    if (origins[b] != currentOrigin)
                    {
                        if (currentAliases != null && aliasOut != null) aliasOut.WriteLine("{\"origin\":\"" + currentOrigin + "\",\"aliases\":{\"epoch\":\"" + currentAliases.EpochHex + "\",\"records\":" + currentAliases.RecordsJson(0, currentAliases.Count) + "}}");
                        encoder?.Dispose(); currentOrigin = origins[b]; currentAliases = new M7Aliases();
                        encoder = new M7EventEncoder(catalog, currentAliases, dictionary, currentOrigin, (Environment.GetEnvironmentVariable("PHASES") == "1" ? (IM7Compressor)new TimedCompressor(new NativeZstdCompressor(dictionary)) : new NativeZstdCompressor(dictionary)));
                    }
                    // V1 path: whole payload gzip level Fastest, as AnalyticsUploader does
                    var text = lines[b];
                    long a0 = GC.GetAllocatedBytesForCurrentThread(); ulong c0 = ThreadCpuNs();
                    var raw = Encoding.UTF8.GetBytes(text);
                    using (var ms = new MemoryStream()) { using (var gz = new GZipStream(ms, CompressionLevel.Fastest, true)) gz.Write(raw, 0, raw.Length); v1Bytes += ms.Length; }
                    ulong c1 = ThreadCpuNs(); long a1 = GC.GetAllocatedBytesForCurrentThread();
                    // parse only
                    long pa0 = a1; ulong pc0 = c1; MiniJson.ParseArray(text); ulong pc1 = ThreadCpuNs(); long pa1 = GC.GetAllocatedBytesForCurrentThread();
                    // V7 encode (includes its own parse)
                    long ea0 = pa1; ulong ec0 = pc1; var wall0 = Stopwatch.GetTimestamp();
                    var r = encoder.Encode(text);
                    var wall1 = Stopwatch.GetTimestamp(); ulong ec1 = ThreadCpuNs(); long ea1 = GC.GetAllocatedBytesForCurrentThread();
                    if (warm++ < 200) continue; // JIT warm-up excluded from the totals
                    batches++; events += counts[b];
                    v1Cpu += c1 - c0; v1Alloc += a1 - a0; parseCpu += pc1 - pc0; parseAlloc += pa1 - pa0;
                    if (r.Ok)
                    {
                        v7Ok++; v7Bytes += r.Frame.Length; v7Cpu += ec1 - ec0; v7Alloc += ea1 - ea0; v7Wall += (ulong)((wall1 - wall0) * 1e9 / Stopwatch.Frequency);
                        perBatchCpu.Add((ec1 - ec0) / (double)counts[b]); perBatchAlloc.Add((ea1 - ea0) / (double)counts[b]); perBatchBytes.Add(r.Frame.Length / (double)counts[b]);
                        packetStream?.Write(currentOrigin); packetStream?.Write(r.Frame.Length); packetStream?.Write(r.Frame);
                    }
                    else { fallback += counts[b]; failures[r.Failure ?? "?"] = failures.TryGetValue(r.Failure ?? "?", out var fc) ? fc + 1 : 1; }
                }
                var cal2 = Calibrate(); if (cal2 < calBest) calBest = cal2;
                var calMean = (cal + cal2) / 2; var chunkEv = events - chunkEvents0; var chunkCpuPerEv = chunkEv > 0 ? (v7Cpu - chunkCpu0) / (double)chunkEv : 0;
                calRows.Add("{\"chunk_events\":" + chunkEv + ",\"calib_ns\":" + calMean.ToString("F3") + ",\"v7_cpu_ns_per_event_raw\":" + chunkCpuPerEv.ToString("F1") + ",\"load\":" + LoadAvg().ToString("F2") + "}");
                if (rssStart == 0) rssStart = proc.WorkingSet64;
                if (events >= maxEvents) done = true;
            }
        }
        if (currentAliases != null && aliasOut != null) aliasOut.WriteLine("{\"origin\":\"" + currentOrigin + "\",\"aliases\":{\"epoch\":\"" + currentAliases.EpochHex + "\",\"records\":" + currentAliases.RecordsJson(0, currentAliases.Count) + "}}");
        aliasOut?.Dispose();
        proc.Refresh();
        double ev1 = Math.Max(events, 1);
        // corrected per-event CPU: each chunk's raw value scaled by calibBest/calibChunk, then median across chunks
        var corr = new List<double>(); var raws = new List<double>();
        foreach (var row in calRows)
        {
            double c = double.Parse(Between(row, "calib_ns\":", ",")), v = double.Parse(Between(row, "v7_cpu_ns_per_event_raw\":", ","));
            if (v > 0) { corr.Add(v * calBest / c); raws.Add(v); }
        }
        string json = "{\"label\":" + Q(label) + ",\"split\":" + Q(split) + ",\"events\":" + events + ",\"batches\":" + batches + ",\"v7_ok_batches\":" + v7Ok + ",\"v7_fallback_events\":" + fallback +
            ",\"v7_bytes_per_event\":" + (v7Bytes / ev1).ToString("F3") + ",\"v1_gzip_bytes_per_event\":" + (v1Bytes / ev1).ToString("F3") +
            ",\"v7_cpu_ns_per_event\":" + (v7Cpu / ev1).ToString("F1") + ",\"v7_cpu_ns_per_event_chunk_median_raw\":" + Median(raws).ToString("F1") + ",\"v7_cpu_ns_per_event_chunk_median_load_corrected\":" + Median(corr).ToString("F1") +
            ",\"v7_wall_ns_per_event\":" + (v7Wall / ev1).ToString("F1") + ",\"v7_alloc_bytes_per_event\":" + (v7Alloc / ev1).ToString("F1") +
            ",\"parse_only_cpu_ns_per_event\":" + (parseCpu / ev1).ToString("F1") + ",\"parse_only_alloc_bytes_per_event\":" + (parseAlloc / ev1).ToString("F1") +
            ",\"v1_gzip_cpu_ns_per_event\":" + (v1Cpu / ev1).ToString("F1") + ",\"v1_gzip_alloc_bytes_per_event\":" + (v1Alloc / ev1).ToString("F1") +
            ",\"p50_v7_cpu_ns_per_event\":" + Pct(perBatchCpu, .5).ToString("F1") + ",\"p95_v7_cpu_ns_per_event\":" + Pct(perBatchCpu, .95).ToString("F1") + ",\"p99_v7_cpu_ns_per_event\":" + Pct(perBatchCpu, .99).ToString("F1") +
            ",\"p50_v7_alloc_per_event\":" + Pct(perBatchAlloc, .5).ToString("F1") + ",\"p95_v7_alloc_per_event\":" + Pct(perBatchAlloc, .95).ToString("F1") +
            ",\"phase_compress_ns_per_event\":" + (TimedCompressor.Ns / ev1).ToString("F1") + ",\"phase_columnar_raw_bytes_per_event\":" + (TimedCompressor.In / ev1).ToString("F2") + ",\"phase_compressed_body_bytes_per_event\":" + (TimedCompressor.Out / ev1).ToString("F2") + ",\"gc_gen0\":" + (GC.CollectionCount(0) - gc0) + ",\"gc_gen1\":" + (GC.CollectionCount(1) - gc1) + ",\"gc_gen2\":" + (GC.CollectionCount(2) - gc2) +
            ",\"rss_start_mb\":" + (rssStart / 1048576.0).ToString("F1") + ",\"peak_working_set_mb\":" + (proc.PeakWorkingSet64 / 1048576.0).ToString("F1") + ",\"managed_heap_mb\":" + (GC.GetTotalMemory(false) / 1048576.0).ToString("F1") +
            ",\"failures\":{" + string.Join(",", System.Linq.Enumerable.Select(failures, kv => Q(kv.Key.Replace("\"", "'")) + ":" + kv.Value)) + "}" + ",\"calib_best_ns\":" + calBest.ToString("F3") + ",\"chunks\":[" + string.Join(",", calRows) + "]}";
        if (outFile != null) File.WriteAllText(outFile, json); else Console.WriteLine(json);
        return 0;
    }

    static string Between(string s, string a, string b) { int i = s.IndexOf(a, StringComparison.Ordinal) + a.Length; int j = s.IndexOf(b, i, StringComparison.Ordinal); return s.Substring(i, j - i); }
    static double Median(List<double> v) { if (v.Count == 0) return 0; var c = new List<double>(v); c.Sort(); return c[c.Count / 2]; }
    static double Pct(List<double> v, double p) { if (v.Count == 0) return 0; var c = new List<double>(v); c.Sort(); return c[(int)(p * (c.Count - 1))]; }
    [DllImport("libc")] private static extern int getloadavg(double[] loads, int n);
    static double LoadAvg() { var l = new double[3]; getloadavg(l, 3); return l[0]; }
}
