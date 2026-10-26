using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using Daliys.Analytics;
using Daliys.Analytics.Internal;
using UnityEngine;
using Unity.Profiling;
using UnityEngine.Profiling;
using Debug = UnityEngine.Debug;

/// <summary>
/// Profiling probe. config.txt: mode=v7|v1|none, scenario=single|burst|persec|perframe, n=events (single/persec/perframe) or rounds (burst),
/// k=events per burst, gap=seconds between single events / bursts, perframe=events per frame (perframe scenario).
/// Output: V7PROF lines (stage table from V7Prof, per-thread CPU, GC counts, memory, timings).
/// </summary>
public sealed class V7ProfProbe : MonoBehaviour
{
    private const string Server = "http://127.0.0.1:18082", Project = "puzzle_gravity_test";
    private readonly List<KeyValuePair<string, Dictionary<string, object>>> _events = new List<KeyValuePair<string, Dictionary<string, object>>>();

    private static long ProcCpuTicks()
    {
        try { var text = File.ReadAllText("/proc/self/stat"); var close = text.LastIndexOf(')'); var f = text.Substring(close + 2).Split(' '); return long.Parse(f[11]) + long.Parse(f[12]); }
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

    private static void Emit(string line) => Debug.Log("V7PROF " + line);

    private ProfilerRecorder _gcBytes, _gcCount; private long _gcBytesSum, _gcCountSum;
    private static long ArtStat(string key)
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        try { using (var d = new AndroidJavaClass("android.os.Debug")) { var v = d.CallStatic<string>("getRuntimeStat", key); return long.Parse(v); } } catch (Exception) { return -1; }
#else
        return -1;
#endif
    }
    private void LateUpdate()
    {
        if (_gcBytes.Valid) _gcBytesSum += _gcBytes.LastValue;
        if (_gcCount.Valid) _gcCountSum += _gcCount.LastValue;
    }
    private void Start()
    {
        _gcBytes = ProfilerRecorder.StartNew(ProfilerCategory.Memory, "GC Allocated In Frame");
        _gcCount = ProfilerRecorder.StartNew(ProfilerCategory.Memory, "GC Allocation In Frame Count");
        StartCoroutine(Run());
    }

    private IEnumerator Run()
    {
        var dir = Application.persistentDataPath;
        var config = new Dictionary<string, string>();
        foreach (var line in File.ReadAllLines(Path.Combine(dir, "config.txt"))) { var p = line.Split('='); if (p.Length == 2) config[p[0].Trim()] = p[1].Trim(); }
        string Cfg(string key, string def) => config.TryGetValue(key, out var v) ? v : def;
        var mode = Cfg("mode", "v7"); var scenario = Cfg("scenario", "perframe");
        var n = int.Parse(Cfg("n", "1200")); var k = int.Parse(Cfg("k", "100")); var gap = float.Parse(Cfg("gap", "6"), CultureInfo.InvariantCulture); var perFrame = int.Parse(Cfg("perframe", "1"));
        var v7 = mode == "v7"; var none = mode == "none";
        var need = scenario == "burst" ? n * k : n;
        foreach (var line in File.ReadLines(Path.Combine(dir, "replay.jsonl")))
        {
            if (_events.Count >= need) break;
            var parsed = Parse(line); _events.Add(new KeyValuePair<string, Dictionary<string, object>>((string)parsed["name"], (Dictionary<string, object>)parsed["props"]));
        }
        Emit("loaded events=" + _events.Count + " mode=" + mode + " scenario=" + scenario + " n=" + n + " k=" + k + " gap=" + gap + " perframe=" + perFrame);

        GC.Collect(); yield return null;
        var calib0 = Calibrate(); var pss0 = PssKb();
        if (!none) Analytics.Initialize(new AnalyticsOptions
        {
            ServerUrl = Server, ProjectId = Project, Environment = "test", DebugLogging = false, UseTransportV7 = v7,
            UploadInterval = TimeSpan.FromSeconds(double.Parse(Cfg("interval_s", "5"), CultureInfo.InvariantCulture)), UploadEventThreshold = int.Parse(Cfg("threshold", "100")),
            MaxPacketEvents = int.Parse(Cfg("packet", "200")), UploadOnBackground = Cfg("bg", "1") == "1", AppVersion = "1.1.14", BuildNumber = "prof-1",
            SessionTimeout = TimeSpan.FromSeconds(double.Parse(Cfg("timeout_s", "300"), CultureInfo.InvariantCulture)),
            EventBufferWindow = TimeSpan.FromMilliseconds(double.Parse(Cfg("buffer_ms", "200"), CultureInfo.InvariantCulture)),
        });
        if (scenario == "forever")
        {
            // lifecycle test: one event per second until the host app kills, backgrounds or relaunches the process
            var i = 0;
            while (true)
            {
                var ev = _events[i++ % _events.Count];
                Analytics.Track(ev.Key, ev.Value);
                if (i % 5 == 0) Emit("forever tracked=" + i);
                yield return new WaitForSeconds(1f);
            }
        }
        yield return new WaitForSeconds(3f);
        // first flush so registration / policy / V7 sync / asset download / alias upload are done before measuring steady state
        if (!none) { var warm = Analytics.FlushAsync(); while (!warm.IsCompleted) yield return null; Analytics.Track(_events[0].Key, _events[0].Value); var w2 = Analytics.FlushAsync(); while (!w2.IsCompleted) yield return null; yield return new WaitForSeconds(2f); }
        V7Prof.Reset();
        var tt0 = ThreadTicks(); var cpu0 = ProcCpuTicks(); var gc0 = GC.CollectionCount(0); var gc1 = GC.CollectionCount(1); var gc2 = GC.CollectionCount(2);
        var mono0 = Profiler.GetMonoUsedSizeLong(); long peakPss = pss0, peakMono = 0;
        var mainAlloc0 = GC.GetAllocatedBytesForCurrentThread(); _gcBytesSum = 0; _gcCountSum = 0; var artBytes0 = ArtStat("art.gc.bytes-allocated"); var artCount0 = ArtStat("art.gc.gc-count"); var artObjs0 = ArtStat("art.gc.objects-allocated");
        var latencies = new List<double>(); var frames = new List<double>(); var wall = Stopwatch.StartNew(); var index = 0; var tracked = 0;

        void TrackOne()
        {
            if (index >= _events.Count) return;
            var ev = _events[index++]; var sw = Stopwatch.StartNew();
            var result = none ? TrackResult.AcceptedToHandoff : Analytics.Track(ev.Key, ev.Value);
            sw.Stop(); latencies.Add(sw.Elapsed.TotalMilliseconds * 1000);
            if (result == TrackResult.AcceptedToHandoff) tracked++;
        }

        if (scenario == "single")
        {
            for (var i = 0; i < n; i++) { var f = Stopwatch.StartNew(); TrackOne(); frames.Add(f.Elapsed.TotalMilliseconds); yield return new WaitForSeconds(gap); }
        }
        else if (scenario == "burst")
        {
            for (var r = 0; r < n; r++)
            {
                var f = Stopwatch.StartNew(); for (var j = 0; j < k; j++) TrackOne(); frames.Add(f.Elapsed.TotalMilliseconds);
                peakPss = Math.Max(peakPss, PssKb()); peakMono = Math.Max(peakMono, Profiler.GetMonoUsedSizeLong());
                yield return new WaitForSeconds(gap);
            }
        }
        else if (scenario == "persec")
        {
            for (var i = 0; i < n; i++) { var f = Stopwatch.StartNew(); TrackOne(); frames.Add(f.Elapsed.TotalMilliseconds); yield return new WaitForSeconds(1f); }
        }
        else
        {
            while (index < n)
            {
                var f = Stopwatch.StartNew(); for (var j = 0; j < perFrame && index < n; j++) TrackOne(); frames.Add(f.Elapsed.TotalMilliseconds);
                if (index % 2000 < perFrame) { peakPss = Math.Max(peakPss, PssKb()); peakMono = Math.Max(peakMono, Profiler.GetMonoUsedSizeLong()); }
                yield return null;
            }
        }
        var scenarioMs = wall.Elapsed.TotalMilliseconds; var cpuScenario = ProcCpuTicks() - cpu0; var mainAlloc = GC.GetAllocatedBytesForCurrentThread() - mainAlloc0;
        var gcScenario = new[] { GC.CollectionCount(0) - gc0, GC.CollectionCount(1) - gc1, GC.CollectionCount(2) - gc2 };
        var cpuBeforeDrain = ProcCpuTicks();
        for (var round = 0; round < 40 && !none; round++)
        {
            var flush = Analytics.FlushAsync(); while (!flush.IsCompleted) yield return null;
            if (flush.Result.Status == FlushStatus.Uploaded && flush.Result.HandoffEventsPending == 0) break;
            yield return new WaitForSeconds(2f);
        }
        var cpuEnd = ProcCpuTicks(); peakPss = Math.Max(peakPss, PssKb());
        latencies.Sort(); frames.Sort();
        double P(List<double> v, double q) => v.Count == 0 ? 0 : v[(int)(q * (v.Count - 1))];
        var ci = CultureInfo.InvariantCulture;
        Emit("summary mode=" + mode + " scenario=" + scenario + " events=" + index + " tracked=" + tracked + " scenario_ms=" + scenarioMs.ToString("F0", ci) +
            " cpu_ticks_scenario=" + cpuScenario + " cpu_ticks_drain=" + (cpuEnd - cpuBeforeDrain) + " cpu_ticks_total=" + (cpuEnd - cpu0) +
            " track_us_p50=" + P(latencies, .5).ToString("F1", ci) + " track_us_p95=" + P(latencies, .95).ToString("F1", ci) + " track_us_p99=" + P(latencies, .99).ToString("F1", ci) + " track_us_max=" + P(latencies, 1).ToString("F1", ci) +
            " frame_ms_p50=" + P(frames, .5).ToString("F2", ci) + " frame_ms_p99=" + P(frames, .99).ToString("F2", ci) + " frame_ms_max=" + P(frames, 1).ToString("F2", ci) +
            " gc0=" + gcScenario[0] + " gc1=" + gcScenario[1] + " gc2=" + gcScenario[2] + " main_alloc_bytes=" + mainAlloc + " alloc_counter_works=" + (mainAlloc > 0 ? 1 : 0) +
            " unity_gc_alloc_bytes_main_frames=" + _gcBytesSum + " unity_gc_alloc_count_main_frames=" + _gcCountSum + " art_bytes_allocated=" + (ArtStat("art.gc.bytes-allocated") - artBytes0) + " art_objects_allocated=" + (ArtStat("art.gc.objects-allocated") - artObjs0) + " art_gc_count=" + (ArtStat("art.gc.gc-count") - artCount0) + " mono_start_kb=" + mono0 / 1024 + " mono_peak_kb=" + peakMono / 1024 + " pss_start_kb=" + pss0 + " pss_peak_kb=" + peakPss + " calib=" + calib0.ToString("F3", ci));
        foreach (var l in V7Prof.Dump().Split('\n')) if (l.Length > 0) Emit(l);
        var tt1 = ThreadTicks(); var dl = new List<KeyValuePair<string, long>>();
        foreach (var kv in tt1) { tt0.TryGetValue(kv.Key, out var b4); if (kv.Value - b4 > 0) dl.Add(new KeyValuePair<string, long>(kv.Key, kv.Value - b4)); }
        dl.Sort((a, b) => b.Value.CompareTo(a.Value)); var tp = new List<string>(); for (var i = 0; i < Math.Min(25, dl.Count); i++) tp.Add(dl[i].Key + "=" + dl[i].Value);
        Emit("threads top=" + string.Join(";", tp));
        Emit("done");
        yield return new WaitForSeconds(2f);
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
