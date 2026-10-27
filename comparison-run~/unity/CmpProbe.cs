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
/// Unified comparison probe: ONE app, ONE event feed, ONE set of measurements for Mortris (V8/V7/V1, unpatched production code) and the competitor SDKs
/// (through bench.CmpAdapter, one SDK per process). config.txt in persistentDataPath: sdk=none|noop|mortris_v8|mortris_v7|mortris_v1|amplitude|amplitude_kotlin|ga|firebase|facebook|adjust|hyperkit_core|hyperkit_ctx|mixpanel
/// scenario=perframe|rate|burst, n, perframe, hz, k, gap, data, host (collector host:port), server (Mortris URL), opts (adapter JSON), tail_max_s, v8content, marker.
/// Result: result.json in persistentDataPath (pulled by the driver). The driver stops the tail by creating stop.txt.
/// </summary>
public sealed class CmpProbe : MonoBehaviour
{
    private readonly List<string> _names = new List<string>();
    private readonly List<Dictionary<string, object>> _props = new List<Dictionary<string, object>>();
    private readonly List<string> _json = new List<string>();
    private readonly Dictionary<string, object> R = new Dictionary<string, object>();

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

    private static double Uptime() { try { return double.Parse(File.ReadAllText("/proc/uptime").Split(' ')[0], CultureInfo.InvariantCulture); } catch (Exception) { return -1; } }

    private static double Calibrate()
    {
        var buf = new int[1 << 20]; ulong acc = 1469598103934665603UL; var sw = Stopwatch.StartNew();
        for (var r = 0; r < 12; r++)
            for (var i = 0; i < buf.Length; i += 7) { acc = (acc ^ (ulong)buf[(i * 31 + r) & (buf.Length - 1)]) * 1099511628211UL; buf[(i * 17) & (buf.Length - 1)] += (int)acc; }
        if (acc == 42) Debug.Log("");
        return sw.Elapsed.TotalMilliseconds * 1e6 / (12.0 * (buf.Length / 7));
    }

    private static int[] Mem()
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        try { using (var info = new AndroidJavaObject("android.os.Debug$MemoryInfo")) using (var debug = new AndroidJavaClass("android.os.Debug")) { debug.CallStatic("getMemoryInfo", info);
            return new[] { info.Call<int>("getTotalPss"), int.Parse(info.Call<string>("getMemoryStat", "summary.java-heap")), int.Parse(info.Call<string>("getMemoryStat", "summary.native-heap")), int.Parse(info.Call<string>("getMemoryStat", "summary.graphics")) }; } }
        catch (Exception) { return new[] { -1, -1, -1, -1 }; }
#else
        return new[] { -1, -1, -1, -1 };
#endif
    }

    private static long ArtStat(string key)
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        try { using (var d = new AndroidJavaClass("android.os.Debug")) { var v = d.CallStatic<string>("getRuntimeStat", key); return long.Parse(v); } } catch (Exception) { return -1; }
#else
        return -1;
#endif
    }

    private static void Emit(string line)
    {
        Debug.Log("CMP " + line);
        // the driver also polls this file: logcat readers can die or miss lines, the file cannot
        try { File.AppendAllText(Path.Combine(Application.persistentDataPath, "state.txt"), line.Split(' ')[0] + "\n"); } catch (Exception) { }
    }

    private ProfilerRecorder _gcBytes, _gcCount; private long _gcBytesSum, _gcCountSum;
    private readonly List<float> _frameDt = new List<float>(); private bool _recordFrames;
    private void LateUpdate()
    {
        if (_gcBytes.Valid) _gcBytesSum += _gcBytes.LastValue;
        if (_gcCount.Valid) _gcCountSum += _gcCount.LastValue;
        if (_recordFrames) _frameDt.Add(Time.unscaledDeltaTime * 1000f);
    }

    private void Start()
    {
        Application.targetFrameRate = 60; QualitySettings.vSyncCount = 0;
        _gcBytes = ProfilerRecorder.StartNew(ProfilerCategory.Memory, "GC Allocated In Frame");
        _gcCount = ProfilerRecorder.StartNew(ProfilerCategory.Memory, "GC Allocation In Frame Count");
        StartCoroutine(Run());
    }

    private static string Json(string s) { var sb = new StringBuilder("\""); foreach (var c in s) { if (c == '"' || c == '\\') sb.Append('\\').Append(c); else if (c < 32) sb.Append("\\u").Append(((int)c).ToString("x4")); else sb.Append(c); } return sb.Append('"').ToString(); }
    private static string ToJson(object v)
    {
        switch (v)
        {
            case null: return "null";
            case bool b: return b ? "true" : "false";
            case string s: return Json(s);
            case long l: return l.ToString(CultureInfo.InvariantCulture);
            case int i: return i.ToString(CultureInfo.InvariantCulture);
            case double d: return d.ToString("R", CultureInfo.InvariantCulture);
            case float f: return f.ToString("R", CultureInfo.InvariantCulture);
            case Dictionary<string, object> m: { var sb = new StringBuilder("{"); var first = true; foreach (var kv in m) { if (!first) sb.Append(','); first = false; sb.Append(Json(kv.Key)).Append(':').Append(ToJson(kv.Value)); } return sb.Append('}').ToString(); }
            case List<double> l2: return "[" + string.Join(",", l2.ConvertAll(x => x.ToString("R", CultureInfo.InvariantCulture))) + "]";
            case List<string> l3: return "[" + string.Join(",", l3.ConvertAll(Json)) + "]";
            default: return Json(v.ToString());
        }
    }
    private static double P(List<double> v, double q) => v.Count == 0 ? 0 : v[(int)(q * (v.Count - 1))];
    private static Dictionary<string, object> Pct(List<double> v)
    {
        v.Sort(); double sum = 0; foreach (var x in v) sum += x;
        return new Dictionary<string, object> { ["n"] = (long)v.Count, ["mean"] = v.Count == 0 ? 0 : sum / v.Count, ["p50"] = P(v, .5), ["p90"] = P(v, .9), ["p95"] = P(v, .95), ["p99"] = P(v, .99), ["p999"] = P(v, .999), ["max"] = P(v, 1) };
    }
    private void Save() { File.WriteAllText(Path.Combine(Application.persistentDataPath, "result.json"), ToJson(R)); }

    private IEnumerator Run()
    {
        var dir = Application.persistentDataPath;
        var config = new Dictionary<string, string>();
        foreach (var line in File.ReadAllLines(Path.Combine(dir, "config.txt"))) { var at = line.IndexOf('='); if (at > 0) config[line.Substring(0, at).Trim()] = line.Substring(at + 1).Trim(); }
        string Cfg(string key, string def) => config.TryGetValue(key, out var v) ? v : def;
        var ci = CultureInfo.InvariantCulture;
        var sdk = Cfg("sdk", "none"); var scenario = Cfg("scenario", "perframe");
        var n = int.Parse(Cfg("n", "3000")); var k = int.Parse(Cfg("k", "100")); var gap = float.Parse(Cfg("gap", "1"), ci); var perFrame = int.Parse(Cfg("perframe", "1")); var hz = double.Parse(Cfg("hz", "10"), ci);
        var tailMax = float.Parse(Cfg("tail_max_s", "600"), ci); var marker = Cfg("marker", "0") == "1"; var v8Content = Cfg("v8content", "0") == "1";
        var host = Cfg("host", "127.0.0.1:18090"); var server = Cfg("server", "http://127.0.0.1:18082"); var project = Cfg("project", "puzzle_gravity_test");
        var progress = Cfg("progress", "0") == "1"; var mortris = sdk.StartsWith("mortris_"); var adapter = !mortris && sdk != "none";
        R["sdk"] = sdk; R["scenario"] = scenario; R["n"] = (long)n; R["perframe"] = (long)perFrame; R["hz"] = hz; R["k"] = (long)k; R["data"] = Cfg("data", "replay.jsonl"); R["device"] = SystemInfo.deviceModel; R["marker"] = marker; R["v8content"] = v8Content;
        R["config"] = new Dictionary<string, object>(); foreach (var kv in config) ((Dictionary<string, object>)R["config"])[kv.Key] = kv.Value;

        var counterOf = new Dictionary<string, Dictionary<string, long>> { ["attempt_id"] = new Dictionary<string, long>(), ["house_run_id"] = new Dictionary<string, long>() };
        var need = scenario == "burst" || scenario == "batch" ? n * k : n;
        foreach (var line in File.ReadLines(Path.Combine(dir, Cfg("data", "replay.jsonl"))))
        {
            if (_names.Count >= need) break;
            var parsed = Parse(line); var props = (Dictionary<string, object>)parsed["props"];
            if (v8Content && mortris)
            {
                props.Remove("wave_attempt_id"); props.Remove("interaction_id"); props.Remove("placed_state_hash");
                foreach (var pair in counterOf)
                    if (props.TryGetValue(pair.Key, out var raw) && raw is string text) { if (!pair.Value.TryGetValue(text, out var number)) pair.Value[text] = number = pair.Value.Count + 1; props[pair.Key] = number; }
            }
            if (marker) props["zz_n"] = (long)_names.Count;
            _names.Add((string)parsed["name"]); _props.Add(props); if (adapter) _json.Add(ToJson(props));
        }
        R["loaded"] = (long)_names.Count;
        Emit("loaded events=" + _names.Count + " sdk=" + sdk + " scenario=" + scenario);
        GC.Collect(); yield return null; yield return new WaitForSeconds(2f);

        AnalyticsProf.Reset();
        var calib0 = Calibrate(); var mem0 = Mem(); R["calib_ns_start"] = calib0; R["prof_compiled"] = AnalyticsProf.Compiled;
        var up0 = Uptime(); var cpuInit0 = ProcCpuTicks(); var swInit = Stopwatch.StartNew(); var monoInit0 = Profiler.GetMonoUsedSizeLong(); var artInit0 = ArtStat("art.gc.bytes-allocated");
        AndroidJavaClass cmp = null;
        if (mortris)
        {
            var opt = new AnalyticsOptions { ServerUrl = server, ProjectId = project, Environment = "test", DebugLogging = Cfg("debug", "0") == "1", AppVersion = "1.1.14", BuildNumber = "cmp-1", UseTransportV7 = sdk == "mortris_v7", UseTransportV8 = sdk == "mortris_v8" };
            if (config.TryGetValue("profile", out var profileName)) opt.UseProfile(profileName == "realtime" ? AnalyticsProfile.Realtime : profileName == "saver" ? AnalyticsProfile.TrafficSaver : AnalyticsProfile.Standard);
            if (config.TryGetValue("adaptive", out var adaptive)) opt.AdaptivePacketSize = adaptive == "1";
            if (config.TryGetValue("queue_mb", out var queueMb)) opt.DurableByteLimit = long.Parse(queueMb, ci) * 1024L * 1024L;
            if (config.TryGetValue("buffer_kb", out var bufferKb)) opt.EventBufferBytes = int.Parse(bufferKb, ci) * 1024;
            if (config.TryGetValue("backlog_packet", out var backlogPacket)) opt.BacklogPacketEvents = int.Parse(backlogPacket, ci);
            if (config.TryGetValue("backlog_pause_ms", out var backlogPause)) opt.BacklogPacketPause = TimeSpan.FromMilliseconds(double.Parse(backlogPause, ci));
            if (config.ContainsKey("interval_s")) opt.UploadInterval = TimeSpan.FromSeconds(double.Parse(config["interval_s"], ci));
            if (config.ContainsKey("threshold")) opt.UploadEventThreshold = int.Parse(config["threshold"]);
            if (config.ContainsKey("packet")) opt.MaxPacketEvents = int.Parse(config["packet"]);
            if (config.ContainsKey("bg")) opt.UploadOnBackground = config["bg"] == "1";
            if (config.ContainsKey("buffer_ms")) opt.EventBufferWindow = TimeSpan.FromMilliseconds(double.Parse(config["buffer_ms"], ci));
            Analytics.Initialize(opt);
        }
        else if (adapter)
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            using (var unity = new AndroidJavaClass("com.unity3d.player.UnityPlayer")) using (var activity = unity.GetStatic<AndroidJavaObject>("currentActivity"))
            { cmp = new AndroidJavaClass("bench.CmpAdapter"); R["adapter_init"] = cmp.CallStatic<string>("init", activity, sdk, host, Cfg("opts", "")); }
#endif
        }
        R["init_ms"] = swInit.Elapsed.TotalMilliseconds; R["init_cpu_ticks"] = ProcCpuTicks() - cpuInit0; R["init_mono_bytes"] = Profiler.GetMonoUsedSizeLong() - monoInit0; R["init_art_bytes"] = ArtStat("art.gc.bytes-allocated") - artInit0;
        // every SDK gets the same settle time after init (GameAnalytics drops events until its async init finished)
        var settle = float.Parse(Cfg("settle_s", "8"), ci); yield return new WaitForSeconds(settle);
        if (mortris) { var warm = Analytics.FlushAsync(); while (!warm.IsCompleted) yield return null; }

        if (AnalyticsProf.Compiled) R["prof_init"] = AnalyticsProf.Dump(true);   // start-up and first flush: init stages, bridge creation, hello, catalog, dictionary
        AnalyticsProf.Reset();
        var pss = Mem(); R["mem_before"] = new List<double> { pss[0], pss[1], pss[2], pss[3] };
        var tt0 = ThreadTicks(); var cpu0 = ProcCpuTicks(); var gc0 = GC.CollectionCount(0); var gc1 = GC.CollectionCount(1); var gc2 = GC.CollectionCount(2);
        var mainAlloc0 = GC.GetAllocatedBytesForCurrentThread(); _gcBytesSum = 0; _gcCountSum = 0; var monoUsed0 = Profiler.GetMonoUsedSizeLong();
        var artBytes0 = ArtStat("art.gc.bytes-allocated"); var artCount0 = ArtStat("art.gc.gc-count"); var artObjs0 = ArtStat("art.gc.objects-allocated");
        var latencies = new List<double>(); var wall = Stopwatch.StartNew(); var index = 0; var tracked = 0; long peakPss = pss[0], peakJava = pss[1], peakNative = pss[2]; double peakMono = 0;
        var frameWork = new List<double>(); _frameDt.Clear(); _recordFrames = true; R["window_start_uptime"] = Uptime(); Emit("window_start up=" + Uptime().ToString("F2", ci));

        void TrackOne()
        {
            if (index >= _names.Count) return;
            var i = index++; var sw = Stopwatch.StartNew();
            if (mortris) { if (Analytics.Track(_names[i], _props[i]) == TrackResult.AcceptedToHandoff) tracked++; }
            else if (adapter) { cmp.CallStatic("track", _names[i], _json[i]); tracked++; }
            sw.Stop(); latencies.Add(sw.Elapsed.TotalMilliseconds * 1000);
            if (progress && index % 10 == 0) File.WriteAllText(Path.Combine(dir, "progress.txt"), index.ToString());
        }
        void Sample() { var m = Mem(); peakPss = Math.Max(peakPss, m[0]); peakJava = Math.Max(peakJava, m[1]); peakNative = Math.Max(peakNative, m[2]); peakMono = Math.Max(peakMono, Profiler.GetMonoUsedSizeLong()); }

        var sampleAt = 0f;
        if (scenario == "burst")
        {
            for (var r = 0; r < n; r++)
            {
                var f = Stopwatch.StartNew(); for (var j = 0; j < k; j++) TrackOne(); frameWork.Add(f.Elapsed.TotalMilliseconds); Sample();
                yield return new WaitForSeconds(gap);
            }
        }
        else if (scenario == "batch")
        {
            // TrackBatchAsync: k events per call, n calls, gap seconds between calls; the frame time is what the call costs the game
            for (var r = 0; r < n; r++)
            {
                var list = new List<BatchEvent>(k); var f = Stopwatch.StartNew();
                for (var j = 0; j < k && index < _names.Count; j++, index++) list.Add(new BatchEvent(_names[index], _props[index]));
                var task = Analytics.TrackBatchAsync(list); frameWork.Add(f.Elapsed.TotalMilliseconds); var wait = Stopwatch.StartNew();
                while (!task.IsCompleted) yield return null;
                var res = task.Result; tracked += res.Accepted; latencies.Add(wait.Elapsed.TotalMilliseconds * 1000); Sample();
                yield return new WaitForSeconds(gap);
            }
        }
        else if (scenario == "rate")
        {
            double owed = 0; var last = Time.realtimeSinceStartupAsDouble;
            while (index < n)
            {
                var now = Time.realtimeSinceStartupAsDouble; owed += (now - last) * hz; last = now;
                var f = Stopwatch.StartNew(); var c = 0; while (owed >= 1 && index < n) { TrackOne(); owed -= 1; c++; } if (c > 0) frameWork.Add(f.Elapsed.TotalMilliseconds);
                sampleAt += Time.unscaledDeltaTime; if (sampleAt > 1f) { sampleAt = 0; Sample(); }
                yield return null;
            }
        }
        else
        {
            while (index < n)
            {
                var f = Stopwatch.StartNew(); for (var j = 0; j < perFrame && index < n; j++) TrackOne(); frameWork.Add(f.Elapsed.TotalMilliseconds);
                sampleAt += Time.unscaledDeltaTime; if (sampleAt > 1f) { sampleAt = 0; Sample(); }
                yield return null;
            }
        }
        _recordFrames = false; var scenarioMs = wall.Elapsed.TotalMilliseconds; var cpuScenario = ProcCpuTicks() - cpu0; var upEnd = Uptime(); R["window_end_uptime"] = upEnd; Emit("window_end up=" + upEnd.ToString("F2", ci));
        var mainAlloc = GC.GetAllocatedBytesForCurrentThread() - mainAlloc0;
        R["events"] = (long)index; R["tracked"] = (long)tracked; R["scenario_ms"] = scenarioMs; R["cpu_ticks_scenario"] = cpuScenario;
        R["gc_mono"] = new List<double> { GC.CollectionCount(0) - gc0, GC.CollectionCount(1) - gc1, GC.CollectionCount(2) - gc2 };
        R["main_alloc_bytes"] = mainAlloc; R["unity_gc_alloc_bytes_frames"] = _gcBytesSum; R["unity_gc_alloc_count_frames"] = _gcCountSum; R["mono_used_delta"] = Profiler.GetMonoUsedSizeLong() - monoUsed0; R["mono_peak"] = peakMono;
        R["art_bytes_scenario"] = ArtStat("art.gc.bytes-allocated") - artBytes0; R["art_gc_count_scenario"] = ArtStat("art.gc.gc-count") - artCount0; R["art_objects_scenario"] = ArtStat("art.gc.objects-allocated") - artObjs0;
        R["track_us"] = Pct(latencies); R["frame_work_ms"] = Pct(frameWork);
        var fr = new List<double>(); var jank33 = 0; var jank50 = 0; var jank100 = 0; double frSum = 0;
        for (var i = 5; i < _frameDt.Count; i++) { var d = _frameDt[i]; fr.Add(d); frSum += d; if (d > 33.4) jank33++; if (d > 50) jank50++; if (d > 100) jank100++; }
        var frp = Pct(fr); frp["jank33"] = (long)jank33; frp["jank50"] = (long)jank50; frp["jank100"] = (long)jank100; frp["fps_mean"] = fr.Count == 0 ? 0 : 1000.0 * fr.Count / frSum; R["frame_dt_ms"] = frp;
        var tt1 = ThreadTicks(); var dl = new List<KeyValuePair<string, long>>();
        foreach (var kv in tt1) { tt0.TryGetValue(kv.Key, out var b4); if (kv.Value - b4 > 0) dl.Add(new KeyValuePair<string, long>(kv.Key, kv.Value - b4)); }
        dl.Sort((a, b) => b.Value.CompareTo(a.Value)); var tp = new Dictionary<string, object>(); for (var i = 0; i < Math.Min(40, dl.Count); i++) tp[dl[i].Key] = dl[i].Value; R["threads_scenario"] = tp;
        if (AnalyticsProf.Compiled) R["prof_scenario"] = AnalyticsProf.Dump(true);
        Save(); Emit("scenario_done events=" + index + " cpu_ticks=" + cpuScenario + " track_p50=" + P(latencies, .5).ToString("F1", ci) + "us");

        // tail: the SDK works on its own (timers, retries, queues) until the driver sees the delivery settle and creates stop.txt
        var cpuTail0 = ProcCpuTicks(); var tailWatch = Stopwatch.StartNew(); var ttTail0 = ThreadTicks(); var stop = Path.Combine(dir, "stop.txt"); if (File.Exists(stop)) File.Delete(stop);
        var artTail0 = ArtStat("art.gc.bytes-allocated"); var tailMono0 = Profiler.GetMonoUsedSizeLong(); var tailGc0 = GC.CollectionCount(0);
        if (config.ContainsKey("flush_at_end") && config["flush_at_end"] == "1") { if (mortris) { for (var attempt = 0; attempt < 5; attempt++) { var fl = Analytics.FlushAsync(); while (!fl.IsCompleted) yield return null; if (fl.Result.HandoffEventsPending == 0) break; } } else if (adapter) cmp.CallStatic("flush"); }
        var lastEmit = 0f;
        var diag = Cfg("diag", "0") == "1"; var lastDiag = -100f;
        while (!File.Exists(stop) && tailWatch.Elapsed.TotalSeconds < tailMax) { if (diag && mortris && tailWatch.Elapsed.TotalSeconds - lastDiag > 15) { lastDiag = (float)tailWatch.Elapsed.TotalSeconds; var dfl = Analytics.FlushAsync(); while (!dfl.IsCompleted) yield return null; var dg = Analytics.GetDiagnostics(); Emit("diag t=" + lastDiag.ToString("F0", ci) + " status=" + dfl.Result.Status + " handoff=" + dfl.Result.HandoffEventsPending + " invalid=" + dg.InvalidEvents + " dropnewest=" + dg.HandoffDropNewest + " ratelimited=" + dg.RateLimited); } Sample(); if (tailWatch.Elapsed.TotalSeconds - lastEmit > 20) { lastEmit = (float)tailWatch.Elapsed.TotalSeconds; Emit("tail t=" + lastEmit.ToString("F0", ci)); } yield return new WaitForSeconds(1f); }
        var tailS = tailWatch.Elapsed.TotalSeconds; var cpuTail = ProcCpuTicks() - cpuTail0;
        R["tail_s"] = tailS; R["cpu_ticks_tail"] = cpuTail; R["tail_stopped_by_driver"] = File.Exists(stop); R["art_bytes_tail"] = ArtStat("art.gc.bytes-allocated") - artTail0; R["tail_mono_delta"] = Profiler.GetMonoUsedSizeLong() - tailMono0; R["tail_gc0"] = GC.CollectionCount(0) - tailGc0;
        var tt2 = ThreadTicks(); var dl2 = new List<KeyValuePair<string, long>>();
        foreach (var kv in tt2) { ttTail0.TryGetValue(kv.Key, out var b4); if (kv.Value - b4 > 0) dl2.Add(new KeyValuePair<string, long>(kv.Key, kv.Value - b4)); }
        dl2.Sort((a, b) => b.Value.CompareTo(a.Value)); var tp2 = new Dictionary<string, object>(); for (var i = 0; i < Math.Min(40, dl2.Count); i++) tp2[dl2[i].Key] = dl2[i].Value; R["threads_tail"] = tp2;
        Sample(); var memEnd = Mem(); R["mem_peak"] = new List<double> { peakPss, peakJava, peakNative }; R["mem_end"] = new List<double> { memEnd[0], memEnd[1], memEnd[2], memEnd[3] }; R["calib_ns_end"] = Calibrate();
        if (AnalyticsProf.Compiled) R["prof_tail"] = AnalyticsProf.Dump(true);
        if (mortris) { var dg = Analytics.GetDiagnostics(); R["diag"] = new Dictionary<string, object> { ["invalid"] = dg.InvalidEvents, ["handoff_drop"] = dg.HandoffDropNewest, ["queue_evicted"] = dg.QueueEvictedEvents, ["buffer_flushed_by_track"] = dg.BufferFlushedByTrack, ["rate_limited"] = dg.RateLimited }; }
        if (adapter) { try { R["adapter_events"] = cmp.CallStatic<long>("count"); } catch (Exception) { } }
        Save(); Emit("done"); yield return new WaitForSeconds(1.5f);
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
