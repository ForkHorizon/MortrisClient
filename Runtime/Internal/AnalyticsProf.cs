// Stage timers for the profiling build of the SDK (no cost in the shipped build).
using System;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace Daliys.Analytics.Internal
{
    /// <summary>Every stage of the SDK that the profiling build times (see Theory~/profiling-v2/PROFILING_PLAN.md for what each one covers). Order matches <see cref="AnalyticsProf.Names"/>.</summary>
    public enum Stage
    {
        // start-up (main thread, inside Analytics.Initialize) and first-use costs
        InitTotal, InitRuntime, InitLimiter, InitWorker, InitDeviceContext, InitEventContext, InitUploader, InitHttpClient, InitV8Session, InitTimers,
        InitSessionTracker, InitSessionStart, InitLifecycle, BridgeCreate, SessionRecover, CountersLoad,
        // inside AnalyticsDeviceContext.Create (what the 180 ms of init.device_context are made of)
        DeviceApp, DeviceOs, DeviceModel, DeviceCulture, DeviceTimezone,
        // Track() on the calling thread
        TrackTotal, TrackValidate, TrackLimiter, TrackEncode, TrackBuffer, TrackPressureFlush, BatchEncode, BatchWrite,
        // the persistence worker pass
        WorkerPass, WorkerIdleCheck, WorkerAttach, WorkerWriteBuffer, WorkerBufferDrain, WorkerSaveSession, WorkerEvictedRead, WorkerUpload, WorkerDetach, WorkerComplete,
        // calls into the Android queue
        JniEnqueue, JniGetState, JniReadOldest, JniDelete, JniSequenceState, JniMeta, JniSession, JniOther,
        // uploading
        UploadFlush, UploadPolicy, UploadPause, V8Send, V8Hello, V8Catalog, V8Dictionary, V8BuildEncoder, V8Encode, V8Http, V8Interpret, V8Persist, V8Policy,
        V1Build, V1Gzip, V1Http, V1Ack,
        // leaving the game
        PauseTotal, PersistNow,
        Count
    }

    /// <summary>Marks the start of a timed stage (wall clock, thread CPU time, managed heap).</summary>
    public readonly struct ProfToken
    {
        internal readonly long Wall, Cpu, Heap;
        internal ProfToken(long wall, long cpu, long heap) { Wall = wall; Cpu = cpu; Heap = heap; }
    }

    /// <summary>
    /// Stage timers of the SDK. They exist only in a build compiled with the scripting define <c>DALIYS_ANALYTICS_PROFILE</c>; without it every call is empty and
    /// inlined away, so the shipped SDK pays nothing. Per stage: calls, wall time, thread CPU time (CLOCK_THREAD_CPUTIME_ID), managed heap growth across the stage
    /// (an estimate: a collection inside the stage hides it), the longest call and a sample of durations for percentiles; plus a trace of the first stage events
    /// (thread, start, duration) for a timeline, and counters. Stages nest, so their times overlap: read them as a tree, not as a sum.
    /// </summary>
    public static class AnalyticsProf
    {
#if DALIYS_ANALYTICS_PROFILE
        public const bool Compiled = true;
#else
        public const bool Compiled = false;
#endif
        public static readonly string[] Names =
        {
            "init.total", "init.runtime", "init.limiter", "init.worker", "init.device_context", "init.event_context", "init.uploader", "init.http_client", "init.v8_session", "init.timers",
            "init.session_tracker", "init.session_start", "init.lifecycle", "bridge.create", "session.recover", "counters.load",
            "device.app", "device.os", "device.model", "device.culture", "device.timezone",
            "track.total", "track.validate", "track.limiter", "track.encode", "track.buffer", "track.pressure_flush", "batch.encode", "batch.write",
            "worker.pass", "worker.idle_check", "worker.attach", "worker.write_buffer", "worker.buffer_drain", "worker.save_session", "worker.evicted_read", "worker.upload", "worker.detach", "worker.complete",
            "jni.enqueue", "jni.get_state", "jni.read_oldest", "jni.delete", "jni.sequence_state", "jni.meta", "jni.session", "jni.other",
            "upload.flush", "upload.policy", "upload.pause", "v8.send", "v8.hello", "v8.catalog", "v8.dictionary", "v8.build_encoder", "v8.encode", "v8.http", "v8.interpret", "v8.persist", "v8.policy",
            "v1.build", "v1.gzip", "v1.http", "v1.ack",
            "pause.total", "pause.persist_now",
        };

        /// <summary>Counters next to the stages (bytes, events and calls that give the stage times a denominator).</summary>
        public enum Counter { Events, WorkerPasses, WorkerWrites, EventsWritten, Packets, PacketBytes, Requests, Connections, TrackBufferFull, Retries, EventsAccepted, Count }

        public static readonly string[] CounterNames = { "events", "worker_passes", "worker_writes", "events_written", "packets", "packet_bytes", "requests", "connections", "track_buffer_full", "retries", "events_accepted" };

        /// <summary>Set by the worker when the queue exists: returns the Java side's own stage timers (a JSON text) or an empty string.</summary>
        public static Func<string> JavaProfile;

#if DALIYS_ANALYTICS_PROFILE
        private const int SampleCapacity = 4096, TraceCapacity = 16384;
        private static readonly long[] Calls = new long[(int)Stage.Count], WallNs = new long[(int)Stage.Count], CpuNs = new long[(int)Stage.Count], HeapBytes = new long[(int)Stage.Count], MaxNs = new long[(int)Stage.Count];
        private static readonly long[][] Samples = new long[(int)Stage.Count][];
        private static readonly long[] Counters = new long[(int)Counter.Count];
        private static readonly short[] TraceStage = new short[TraceCapacity];
        private static readonly int[] TraceThread = new int[TraceCapacity];
        private static readonly long[] TraceStartUs = new long[TraceCapacity], TraceDurUs = new long[TraceCapacity];
        private static int _traceCount;
        private static long _origin = System.Diagnostics.Stopwatch.GetTimestamp();
        private static readonly double TicksToNs = 1e9 / System.Diagnostics.Stopwatch.Frequency;

#if UNITY_ANDROID && !UNITY_EDITOR
        [StructLayout(LayoutKind.Sequential)] private struct Timespec { public long Sec; public long Nsec; }
        [DllImport("libc", EntryPoint = "clock_gettime")] private static extern int ClockGettime(int clock, out Timespec ts);
        private static long ThreadCpuNs() { try { return ClockGettime(3, out var ts) == 0 ? ts.Sec * 1000000000L + ts.Nsec : 0; } catch (Exception) { return 0; } }
#else
        private static long ThreadCpuNs() => 0;   // only the Android player has a per-thread CPU clock here; wall time and heap are still recorded
#endif

        private static bool Traced(Stage s) => s < Stage.TrackTotal || (s >= Stage.WorkerPass && s <= Stage.WorkerComplete) || (s >= Stage.UploadFlush && s <= Stage.PersistNow);
#endif

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public static ProfToken Begin()
        {
#if DALIYS_ANALYTICS_PROFILE
            return new ProfToken(System.Diagnostics.Stopwatch.GetTimestamp(), ThreadCpuNs(), GC.GetTotalMemory(false));
#else
            return default;
#endif
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public static void End(Stage stage, ProfToken token)
        {
#if DALIYS_ANALYTICS_PROFILE
            var endWall = System.Diagnostics.Stopwatch.GetTimestamp();
            var wallNs = (long)((endWall - token.Wall) * TicksToNs);
            var cpu = ThreadCpuNs() - token.Cpu;
            var heap = GC.GetTotalMemory(false) - token.Heap;
            var i = (int)stage;
            var n = Interlocked.Increment(ref Calls[i]);
            Interlocked.Add(ref WallNs[i], wallNs);
            Interlocked.Add(ref CpuNs[i], cpu);
            if (heap > 0) Interlocked.Add(ref HeapBytes[i], heap);
            long seen;
            while (wallNs > (seen = Interlocked.Read(ref MaxNs[i])) && Interlocked.CompareExchange(ref MaxNs[i], wallNs, seen) != seen) { }
            if (n <= SampleCapacity)
            {
                var samples = Samples[i] ?? Interlocked.CompareExchange(ref Samples[i], new long[SampleCapacity], null) ?? Samples[i];
                samples[n - 1] = wallNs;
            }
            if (Traced(stage))
            {
                var slot = Interlocked.Increment(ref _traceCount) - 1;
                if (slot < TraceCapacity)
                {
                    TraceStage[slot] = (short)i; TraceThread[slot] = Thread.CurrentThread.ManagedThreadId;
                    TraceStartUs[slot] = (long)((token.Wall - _origin) * TicksToNs / 1000); TraceDurUs[slot] = wallNs / 1000;
                }
            }
#endif
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public static void Count(Counter counter, long value = 1)
        {
#if DALIYS_ANALYTICS_PROFILE
            Interlocked.Add(ref Counters[(int)counter], value);
#endif
        }

        /// <summary>Forgets everything recorded so far (the scenario starts here); the trace origin moves to now.</summary>
        public static void Reset()
        {
#if DALIYS_ANALYTICS_PROFILE
            for (var i = 0; i < (int)Stage.Count; i++) { Calls[i] = WallNs[i] = CpuNs[i] = HeapBytes[i] = MaxNs[i] = 0; Samples[i] = null; }
            for (var i = 0; i < Counters.Length; i++) Counters[i] = 0;
            _traceCount = 0; _origin = System.Diagnostics.Stopwatch.GetTimestamp();
#endif
        }

        /// <summary>
        /// Text report. Lines: <c>S|name|calls|wall_us|cpu_us|heap_bytes|max_us|p50_us|p99_us</c> (totals), <c>C|name|value</c>, <c>T|stage|thread|start_us|dur_us</c> (the trace, in order of
        /// completion) and <c>J|json</c> for the Java side. Empty when the SDK was built without the profiling define.
        /// </summary>
        public static string Dump(bool includeTrace = true)
        {
#if DALIYS_ANALYTICS_PROFILE
            var sb = new StringBuilder();
            for (var i = 0; i < (int)Stage.Count; i++)
            {
                var calls = Interlocked.Read(ref Calls[i]);
                if (calls == 0) continue;
                long p50 = 0, p99 = 0;
                var samples = Samples[i];
                if (samples != null)
                {
                    var count = (int)Math.Min(calls, SampleCapacity);
                    var copy = new long[count]; Array.Copy(samples, copy, count); Array.Sort(copy);
                    p50 = copy[count / 2] / 1000; p99 = copy[(int)(0.99 * (count - 1))] / 1000;
                }
                sb.Append("S|").Append(Names[i]).Append('|').Append(calls).Append('|').Append(WallNs[i] / 1000).Append('|').Append(CpuNs[i] / 1000).Append('|').Append(HeapBytes[i])
                  .Append('|').Append(MaxNs[i] / 1000).Append('|').Append(p50).Append('|').Append(p99).Append('\n');
            }
            for (var i = 0; i < Counters.Length; i++) if (Counters[i] != 0) sb.Append("C|").Append(CounterNames[i]).Append('|').Append(Counters[i]).Append('\n');
            if (includeTrace)
            {
                var n = Math.Min(Volatile.Read(ref _traceCount), TraceCapacity);
                for (var i = 0; i < n; i++) sb.Append("T|").Append(Names[TraceStage[i]]).Append('|').Append(TraceThread[i]).Append('|').Append(TraceStartUs[i]).Append('|').Append(TraceDurUs[i]).Append('\n');
            }
            try { var java = JavaProfile?.Invoke(); if (!string.IsNullOrEmpty(java)) sb.Append("J|").Append(java).Append('\n'); } catch (Exception) { }
            return sb.ToString();
#else
            return string.Empty;
#endif
        }
    }
}
