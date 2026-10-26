using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using Daliys.Analytics;
using UnityEngine;
using UnityEngine.Profiling;
using Debug = UnityEngine.Debug;

/// <summary>
/// Replays real events (names + flat properties, from replay.jsonl next to the app data) through the SDK and logs CPU/memory/GC numbers (V7PERF lines).
/// config.txt in the same folder: mode=v7|v1, n=<events>, perframe=<events per frame>. CPU comes from /proc/self/stat (10 ms ticks, whole process).
/// </summary>
public sealed class V7PerfProbe : MonoBehaviour
{
    private const string Server = "http://10.0.2.2:18082", Project = "puzzle_gravity_test";
    private readonly List<KeyValuePair<string, Dictionary<string, object>>> _events = new List<KeyValuePair<string, Dictionary<string, object>>>();

    private static long ProcCpuTicks()
    {
        try
        {
            var text = File.ReadAllText("/proc/self/stat"); var close = text.LastIndexOf(')'); var f = text.Substring(close + 2).Split(' ');
            return long.Parse(f[11]) + long.Parse(f[12]); // utime + stime (fields 14,15; index shifted by 3)
        }
        catch (Exception) { return -1; }
    }

    private static Dictionary<string, long> ThreadTicks()
    {
        var map = new Dictionary<string, long>();
        try
        {
            foreach (var dir in Directory.GetDirectories("/proc/self/task"))
            {
                var text = File.ReadAllText(dir + "/stat"); var close = text.LastIndexOf(')'); var open = text.IndexOf('('); var f = text.Substring(close + 2).Split(' ');
                map[Path.GetFileName(dir) + ":" + text.Substring(open + 1, close - open - 1)] = long.Parse(f[11]) + long.Parse(f[12]);
            }
        }
        catch (Exception) { }
        return map;
    }

    private static double Calibrate()
    {
        var buf = new int[1 << 20]; ulong acc = 1469598103934665603UL; var sw = Stopwatch.StartNew();
        for (var r = 0; r < 12; r++)
            for (var i = 0; i < buf.Length; i += 7) { acc = (acc ^ (ulong)buf[(i * 31 + r) & (buf.Length - 1)]) * 1099511628211UL; buf[(i * 17) & (buf.Length - 1)] += (int)acc; }
        if (acc == 42) Debug.Log("");
        return sw.Elapsed.TotalMilliseconds * 1e6 / (12.0 * (buf.Length / 7));
    }

    private static long PssKb()
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        try { using (var debug = new AndroidJavaClass("android.os.Debug")) using (var info = new AndroidJavaObject("android.os.Debug$MemoryInfo")) { debug.CallStatic("getMemoryInfo", info); return info.Call<int>("getTotalPss"); } }
        catch (Exception) { return -1; }
#else
        return -1;
#endif
    }

    private void Start() => StartCoroutine(Run());

    private IEnumerator Run()
    {
        var dir = Application.persistentDataPath;
        var config = new Dictionary<string, string>();
        foreach (var line in File.ReadAllLines(Path.Combine(dir, "config.txt"))) { var p = line.Split('='); if (p.Length == 2) config[p[0].Trim()] = p[1].Trim(); }
        var v7 = config.TryGetValue("mode", out var mode) && mode == "v7"; var none = mode == "none";
        var n = config.TryGetValue("n", out var ns) ? int.Parse(ns) : 20000;
        var perFrame = config.TryGetValue("perframe", out var pf) ? int.Parse(pf) : 20;
        foreach (var line in File.ReadLines(Path.Combine(dir, "replay.jsonl")))
        {
            if (_events.Count >= n) break;
            var parsed = Parse(line); _events.Add(new KeyValuePair<string, Dictionary<string, object>>((string)parsed["name"], (Dictionary<string, object>)parsed["props"]));
        }
        Debug.Log("V7PERF loaded events=" + _events.Count + " mode=" + mode);

        GC.Collect(); yield return null;
        var calib0 = Calibrate(); var pss0 = PssKb(); var heap0 = GC.GetTotalMemory(true);
        if (!none) Analytics.Initialize(new AnalyticsOptions
        {
            ServerUrl = Server, ProjectId = Project, Environment = "test", DebugLogging = false, UseTransportV7 = v7,
            UploadInterval = TimeSpan.FromSeconds(5), UploadEventThreshold = 100, AppVersion = "1.1.14", BuildNumber = "perf-1",
        });
        yield return new WaitForSeconds(3f);
        if (config.TryGetValue("hold", out var holdText))
        {
            // idle window: SDK initialised, nothing tracked. Per-thread CPU shows who burns time while the game does nothing.
            var t0 = ThreadTicks(); var c0 = ProcCpuTicks(); var hold = int.Parse(holdText); yield return new WaitForSeconds(hold); var t1 = ThreadTicks(); var c1 = ProcCpuTicks();
            var deltas = new List<KeyValuePair<string, long>>();
            foreach (var kv in t1) { t0.TryGetValue(kv.Key, out var before); if (kv.Value - before > 0) deltas.Add(new KeyValuePair<string, long>(kv.Key, kv.Value - before)); }
            deltas.Sort((a, b) => b.Value.CompareTo(a.Value));
            var top = new List<string>(); for (var i = 0; i < Math.Min(8, deltas.Count); i++) top.Add(deltas[i].Key + "=" + deltas[i].Value);
            Debug.Log("V7PERF idle mode=" + mode + " hold_s=" + hold + " cpu_ticks=" + (c1 - c0) + " threads=" + t1.Count + " top=" + string.Join(";", top));
            Application.Quit(); yield break;
        }
        var tt0 = ThreadTicks(); var cpu0 = ProcCpuTicks(); var gc0 = GC.CollectionCount(0); var gc1 = GC.CollectionCount(1); var gc2 = GC.CollectionCount(2);
        var mono0 = Profiler.GetMonoUsedSizeLong(); var total0 = Profiler.GetTotalAllocatedMemoryLong();
        var latencies = new List<double>(_events.Count); var frames = new List<double>(); var calibs = new List<double>();
        long peakPss = pss0, peakMono = 0; var accepted = 0; var full = 0; var other = 0;
        var wall = Stopwatch.StartNew(); var index = 0;
        while (index < _events.Count)
        {
            var frame = Stopwatch.StartNew();
            for (var k = 0; k < perFrame && index < _events.Count; k++)
            {
                var ev = _events[index]; var sw = Stopwatch.StartNew();
                var result = none ? TrackResult.AcceptedToHandoff : Analytics.Track(ev.Key, ev.Value);
                sw.Stop();
                if (result == TrackResult.AcceptedToHandoff) { accepted++; index++; latencies.Add(sw.Elapsed.TotalMilliseconds * 1000); }
                else if (result == TrackResult.HandoffFull) { full++; break; }
                else { other++; index++; }
            }
            frames.Add(frame.Elapsed.TotalMilliseconds);
            if (index % 2000 < perFrame) { calibs.Add(Calibrate()); peakPss = Math.Max(peakPss, PssKb()); peakMono = Math.Max(peakMono, Profiler.GetMonoUsedSizeLong()); }
            yield return null;
        }
        var replayMs = wall.Elapsed.TotalMilliseconds; var cpuReplay = ProcCpuTicks() - cpu0;
        { var tt1 = ThreadTicks(); var dl = new List<KeyValuePair<string, long>>(); foreach (var kv in tt1) { tt0.TryGetValue(kv.Key, out var b4); if (kv.Value - b4 > 0) dl.Add(new KeyValuePair<string, long>(kv.Key, kv.Value - b4)); }
          dl.Sort((a, b) => b.Value.CompareTo(a.Value)); var tp = new List<string>(); for (var i = 0; i < Math.Min(40, dl.Count); i++) tp.Add(dl[i].Key + "=" + dl[i].Value); Debug.Log("V7PERF threads mode=" + mode + " replay_ms=" + replayMs.ToString("F0") + " top=" + string.Join(";", tp)); }
        var gcReplay = new[] { GC.CollectionCount(0) - gc0, GC.CollectionCount(1) - gc1, GC.CollectionCount(2) - gc2 };
        var monoReplay = Profiler.GetMonoUsedSizeLong();
        // drain: keep flushing until everything is uploaded, so background CPU for encode/compress/HTTP is included
        var drain = Stopwatch.StartNew(); var cpuBeforeDrain = ProcCpuTicks();
        // The SDK's own timer uploads (UploadInterval 5 s); we only look at the state every 5 s so the probe does not add load. The server allows an installation
        // a burst of 30 batches, so runs stay at <= 2800 events and never hit its 429 limit.
        for (var round = 0; round < 40; round++)
        {
            if (none) { if (round >= 2) break; yield return new WaitForSeconds(5f); continue; }
            var flush = Analytics.FlushAsync();
            while (!flush.IsCompleted) yield return null;
            if (flush.Result.Status == FlushStatus.Uploaded && flush.Result.HandoffEventsPending == 0) break;
            yield return new WaitForSeconds(5f);
        }
        var cpuEnd = ProcCpuTicks(); peakPss = Math.Max(peakPss, PssKb());
        latencies.Sort(); frames.Sort();
        double P(List<double> v, double q) => v.Count == 0 ? 0 : v[(int)(q * (v.Count - 1))];
        var ci = CultureInfo.InvariantCulture;
        Debug.Log("V7PERF result mode=" + (v7 ? "v7" : "v1") + " events=" + _events.Count + " accepted=" + accepted + " handoff_full_retries=" + full + " other_results=" + other +
            " replay_ms=" + replayMs.ToString("F0", ci) + " drain_ms=" + drain.ElapsedMilliseconds + " cpu_ticks_replay=" + cpuReplay + " cpu_ticks_drain=" + (cpuEnd - cpuBeforeDrain) + " cpu_ticks_total=" + (cpuEnd - cpu0) +
            " track_us_p50=" + P(latencies, .5).ToString("F1", ci) + " track_us_p95=" + P(latencies, .95).ToString("F1", ci) + " track_us_p99=" + P(latencies, .99).ToString("F1", ci) + " track_us_max=" + P(latencies, 1).ToString("F1", ci) +
            " frame_ms_p50=" + P(frames, .5).ToString("F2", ci) + " frame_ms_p99=" + P(frames, .99).ToString("F2", ci) + " frame_ms_max=" + P(frames, 1).ToString("F2", ci) +
            " gc0=" + gcReplay[0] + " gc1=" + gcReplay[1] + " gc2=" + gcReplay[2] + " mono_start_kb=" + mono0 / 1024 + " mono_end_replay_kb=" + monoReplay / 1024 + " mono_peak_kb=" + peakMono / 1024 +
            " unity_total_start_kb=" + total0 / 1024 + " unity_total_end_kb=" + Profiler.GetTotalAllocatedMemoryLong() / 1024 + " pss_start_kb=" + pss0 + " pss_peak_kb=" + peakPss + " heap_start_kb=" + heap0 / 1024 +
            " calib_start=" + calib0.ToString("F3", ci) + " calibs=" + string.Join(",", calibs.ConvertAll(c => c.ToString("F3", ci))));
        yield return new WaitForSeconds(3f);
        Application.Quit();
    }

    // Minimal JSON parser for the replay file: {"name":..,"props":{flat values}}
    private static Dictionary<string, object> Parse(string s) { var i = 0; return (Dictionary<string, object>)Value(s, ref i); }
    private static object Value(string s, ref int i)
    {
        while (s[i] == ' ') i++;
        switch (s[i])
        {
            case '{':
            {
                var map = new Dictionary<string, object>(); i++;
                while (true)
                {
                    while (s[i] == ' ' || s[i] == ',') i++;
                    if (s[i] == '}') { i++; return map; }
                    var key = (string)Value(s, ref i); while (s[i] == ' ' || s[i] == ':') i++;
                    map[key] = Value(s, ref i);
                }
            }
            case '"':
            {
                var sb = new StringBuilder(); i++;
                while (s[i] != '"')
                {
                    if (s[i] == '\\')
                    {
                        i++;
                        switch (s[i]) { case 'n': sb.Append('\n'); break; case 't': sb.Append('\t'); break; case 'r': sb.Append('\r'); break; case 'b': sb.Append('\b'); break; case 'f': sb.Append('\f'); break;
                            case 'u': sb.Append((char)Convert.ToInt32(s.Substring(i + 1, 4), 16)); i += 4; break; default: sb.Append(s[i]); break; }
                        i++;
                    }
                    else sb.Append(s[i++]);
                }
                i++; return sb.ToString();
            }
            case 't': i += 4; return true;
            case 'f': i += 5; return false;
            case 'n': i += 4; return null;
            default:
            {
                var start = i; while (i < s.Length && "+-0123456789.eE".IndexOf(s[i]) >= 0) i++;
                var text = s.Substring(start, i - start);
                if (text.IndexOfAny(new[] { '.', 'e', 'E' }) < 0 && long.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out var l)) return l;
                return double.Parse(text, CultureInfo.InvariantCulture);
            }
        }
    }
}
