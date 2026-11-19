// Stage timers of the Android queue: off by default, turned on by the profiling build of the Unity SDK.
package com.daliys.analytics;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.Arrays;

/** Per-stage timers (one boolean test per stage while off). Not thread-safe: the queue calls it under its own lock. */
final class QueueProfiler {
    static final String[] NAMES = {"enq.total", "enq.insert_loop", "enq.insert_exec", "enq.meta_sequence", "enq.expire", "enq.bounds", "enq.counters", "enq.commit",
        "read.total", "read.query", "delete.total", "state", "sequence_state", "meta_get", "meta_set", "session_save", "session_load"};
static final int P_ENQ = 0, P_INSERT_LOOP = 1, P_INSERT_EXEC = 2, P_META_SEQ = 3, P_EXPIRE = 4, P_BOUNDS = 5, P_COUNTERS = 6, P_COMMIT = 7, P_READ = 8, P_READ_QUERY = 9,
        P_DELETE = 10, P_STATE = 11, P_SEQ_STATE = 12, P_META_GET = 13, P_META_SET = 14, P_SESSION_SAVE = 15, P_SESSION_LOAD = 16;
    private boolean enabled;
    private final long[] calls = new long[NAMES.length], wall = new long[NAMES.length], cpu = new long[NAMES.length], alloc = new long[NAMES.length],
            max = new long[NAMES.length];

    void setEnabled(boolean on) {
        enabled = on;
        Arrays.fill(calls, 0); Arrays.fill(wall, 0); Arrays.fill(cpu, 0); Arrays.fill(alloc, 0); Arrays.fill(max, 0);
    }

    String json() throws JSONException {
        JSONObject root = new JSONObject();
        for (int i = 0; i < NAMES.length; i++) {
            if (calls[i] == 0) continue;
            root.put(NAMES[i], new JSONArray().put(calls[i]).put(wall[i]).put(cpu[i]).put(alloc[i]).put(max[i]));
        }
        return root.toString();
    }

    long begin() { return enabled ? System.nanoTime() : 0L; }
    long cpuBegin() { return enabled ? android.os.Debug.threadCpuTimeNanos() : 0L; }
    long allocBegin() {
        if (!enabled) return 0L;
        try { return Long.parseLong(android.os.Debug.getRuntimeStat("art.gc.bytes-allocated")); } catch (RuntimeException ignored) { return 0L; }
    }

    void end(int stage, long t0) {
        if (!enabled) return;
        long d = System.nanoTime() - t0;
        calls[stage]++; wall[stage] += d; if (d > max[stage]) max[stage] = d;
    }

    void endTotal(int stage, long t0, long cpu0, long alloc0) {
        if (!enabled) return;
        end(stage, t0);
        cpu[stage] += android.os.Debug.threadCpuTimeNanos() - cpu0;
        long after = allocBegin();
        if (after > alloc0) alloc[stage] += after - alloc0;
    }
}
