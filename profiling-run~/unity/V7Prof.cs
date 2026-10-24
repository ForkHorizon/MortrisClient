using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace Daliys.Analytics.Internal
{
    /// <summary>Profiling-only instrumentation, present in the patched SDK copy used by profiling-run~, never in the shipped package.
    /// Per stage: wall ns, thread CPU ns (CLOCK_THREAD_CPUTIME_ID), bytes allocated by the thread, calls. Stages are inclusive and may nest.</summary>
    public static class V7Prof
    {
        public const int TrackTotal = 0, TrackEnqueue = 1, PersistTotal = 2, Snapshot = 3, Serialize = 4, JniEnqueueBatch = 5, RemovePrefix = 6, UploaderFlush = 7,
            JniGetState = 8, JniReadBatch = 9, JniDeleteAck = 10, V7Encode = 11, V7PostPacket = 12, V1ParseQueued = 13, V1SendBatch = 14, V7SendTotal = 15,
            V1Gzip = 16, HttpSend = 17, JniOther = 18, Count = 19;
        public static readonly string[] Names = { "track_total", "track_enqueue", "persist_total", "snapshot_batch", "serialize_json", "jni_enqueue_batch", "remove_prefix",
            "uploader_flush", "jni_get_state", "jni_read_batch", "jni_delete_ack", "v7_encode(parse+pack+zstd)", "v7_post_packet", "v1_parse_queued", "v1_send_batch(json+gzip+http)",
            "v7_send_total", "v1_gzip_body", "http_send(wall)", "jni_other" };
        // counters
        public const int PersistCalls = 0, PersistEvents = 1, FlushCalls = 2, BytesV7 = 3, BytesV1Gzip = 4, BytesV1Json = 5, Packets = 6, Batches = 7, ScheduleCalls = 8;
        public static readonly string[] CounterNames = { "persist_calls", "persist_events", "flush_calls", "bytes_v7_packets", "bytes_v1_gzip_bodies", "bytes_v1_json_bodies", "v7_packets", "v1_batches", "schedule_calls" };

        private static readonly long[] Wall = new long[Count], Cpu = new long[Count], Alloc = new long[Count], Calls = new long[Count], Counters = new long[16];
        public static volatile bool Enabled = true;

        [StructLayout(LayoutKind.Sequential)] private struct Timespec { public long Sec; public long Nsec; }
        [DllImport("libc", EntryPoint = "clock_gettime")] private static extern int ClockGettime(int clock, out Timespec ts);
        private static long ThreadCpuNs() { try { return ClockGettime(3, out var ts) == 0 ? ts.Sec * 1000000000L + ts.Nsec : 0; } catch (Exception) { return 0; } }

        public struct Token { internal long Wall, Cpu, Alloc; }
        public static Token Begin()
        {
            Token t;
            t.Wall = System.Diagnostics.Stopwatch.GetTimestamp(); t.Cpu = ThreadCpuNs(); t.Alloc = GC.GetTotalMemory(false);
            return t;
        }
        public static void End(int stage, Token t)
        {
            var wall = System.Diagnostics.Stopwatch.GetTimestamp() - t.Wall; var cpu = ThreadCpuNs() - t.Cpu; var alloc = Math.Max(0, GC.GetTotalMemory(false) - t.Alloc); // managed heap growth across the stage: an estimate (a collection inside the stage hides it)
            Interlocked.Add(ref Wall[stage], wall * 1000000000L / System.Diagnostics.Stopwatch.Frequency); Interlocked.Add(ref Cpu[stage], cpu);
            Interlocked.Add(ref Alloc[stage], alloc); Interlocked.Increment(ref Calls[stage]);
        }
        public static T Timed<T>(int stage, Func<T> f) { var t = Begin(); try { return f(); } finally { End(stage, t); } }
        public static void Add(int counter, long v) => Interlocked.Add(ref Counters[counter], v);
        public static void Reset() { for (var i = 0; i < Count; i++) { Wall[i] = Cpu[i] = Alloc[i] = Calls[i] = 0; } for (var i = 0; i < Counters.Length; i++) Counters[i] = 0; }
        public static long Counter(int c) => Interlocked.Read(ref Counters[c]);

        /// <summary>One line per stage: name|calls|wall_us_total|cpu_us_total|alloc_bytes_total (totals; the caller divides by events).</summary>
        public static string Dump()
        {
            var sb = new StringBuilder();
            for (var i = 0; i < Count; i++) if (Calls[i] > 0) sb.Append("S|").Append(Names[i]).Append('|').Append(Calls[i]).Append('|').Append(Wall[i] / 1000).Append('|').Append(Cpu[i] / 1000).Append('|').Append(Alloc[i]).Append('\n');
            for (var i = 0; i < CounterNames.Length; i++) if (Counters[i] != 0) sb.Append("C|").Append(CounterNames[i]).Append('|').Append(Counters[i]).Append('\n');
            return sb.ToString();
        }
    }
}
