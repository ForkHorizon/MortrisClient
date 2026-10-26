package bench;

import android.app.Activity;
import android.os.Bundle;
import android.util.Log;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;
import org.json.JSONObject;

/** Replays a JSONL corpus ({"name":..,"props":{..}}) through ONE SDK per process.
 *  Extras: sdk=none|amplitude|ga, host=10.0.2.2:PORT, hz=events/s, tail=seconds to wait after replay,
 *  amp_threshold / amp_period_ms (optional tuned mode). Default shipping config when omitted. */
public class Main extends Activity {
    static int marker = 0;
    static final String TAG = "BENCH";
    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        final String sdk = getIntent().getStringExtra("sdk");
        final String host = getIntent().getStringExtra("host");
        final int hz = getIntent().getIntExtra("hz", 10);
        final int tail = getIntent().getIntExtra("tail", 45);
        final int thr = getIntent().getIntExtra("amp_threshold", -1);
        final int per = getIntent().getIntExtra("amp_period_ms", -1);
        final int maxEvents = getIntent().getIntExtra("n", 600);
        final int batch = getIntent().getIntExtra("amp_batch", -1); marker = getIntent().getIntExtra("marker", 0);
        new Thread(() -> run(sdk, host, hz, tail, thr, per, maxEvents, batch)).start();
    }

    /** Fixed mixed workload (same shape as the host bench): ns per iteration of thread CPU time. Detects contention from the host/guest. */
    static double calibrate() {
        int[] buf = new int[1 << 20]; long acc = 1469598103934665603L; long t0 = android.os.Debug.threadCpuTimeNanos();
        for (int r = 0; r < 12; r++) for (int i = 0; i < buf.length; i += 7) { acc = (acc ^ buf[(i * 31 + r) & (buf.length - 1)]) * 1099511628211L; buf[(i * 17) & (buf.length - 1)] += (int) acc; }
        long t1 = android.os.Debug.threadCpuTimeNanos(); if (acc == 42) Log.i(TAG, ""); return (t1 - t0) / (12.0 * (buf.length / 7));
    }
    static volatile long peakPssKb = 0, peakJavaKb = 0, peakNativeKb = 0; static volatile boolean sampling = true;
    static void startSampler() {
        Thread t = new Thread(() -> { while (sampling) {
            try { android.os.Debug.MemoryInfo mi = new android.os.Debug.MemoryInfo(); android.os.Debug.getMemoryInfo(mi);
                peakPssKb = Math.max(peakPssKb, mi.getTotalPss()); Runtime rt = Runtime.getRuntime(); peakJavaKb = Math.max(peakJavaKb, (rt.totalMemory() - rt.freeMemory()) / 1024);
                peakNativeKb = Math.max(peakNativeKb, android.os.Debug.getNativeHeapAllocatedSize() / 1024); Thread.sleep(250); } catch (Throwable e) { } } });
        t.setDaemon(true); t.start();
    }
    static final java.util.Map<String, String> TOKENS = new java.util.HashMap<>();
    static String adjustToken(String name) { String t = TOKENS.get(name); if (t == null) { t = String.format("%06x", TOKENS.size() + 0x100001).substring(0, 6).replace('0', 'a'); TOKENS.put(name, t); } return t; }
    static long[] snap() {
        long alloc = 0, gc = 0;
        try { alloc = Long.parseLong(android.os.Debug.getRuntimeStat("art.gc.bytes-allocated")); gc = Long.parseLong(android.os.Debug.getRuntimeStat("art.gc.gc-count")); } catch (Throwable t) { }
        return new long[] { android.os.Process.getElapsedCpuTime(), alloc, gc };
    }

    void run(String sdk, String host, int hz, int tail, int thr, int per, int maxEvents, int batch) {
        try {
            File f = new File(getExternalFilesDir(null), "replay.jsonl");
            startSampler();
            calibrate(); calibrate(); calibrate(); double cal0 = calibrate(); double calBest = cal0; StringBuilder cals = new StringBuilder();
            long pssStart; { android.os.Debug.MemoryInfo mi = new android.os.Debug.MemoryInfo(); android.os.Debug.getMemoryInfo(mi); pssStart = mi.getTotalPss(); }
            long[] m0 = snap();
            com.amplitude.api.AmplitudeClient amp = null; com.google.firebase.analytics.FirebaseAnalytics fa = null; com.facebook.appevents.AppEventsLogger fb = null;
            if ("amplitude".equals(sdk)) {
                amp = com.amplitude.api.Amplitude.getInstance();
                amp.initialize(this, "FAKE_API_KEY_0000000000000000").setServerUrl("http://" + host + "/amp");
                if (thr > 0) amp.setEventUploadThreshold(thr);
                if (per > 0) amp.setEventUploadPeriodMillis(per);
                if (batch > 0) amp.setEventUploadMaxBatchSize(batch);
                amp.setUserId("u-bench-1");
            } else if ("firebase".equals(sdk)) {
                fa = com.google.firebase.analytics.FirebaseAnalytics.getInstance(this);
                fa.setAnalyticsCollectionEnabled(true);
            } else if ("adjust".equals(sdk)) {
                com.adjust.sdk.AdjustConfig ac = new com.adjust.sdk.AdjustConfig(this, "abcdefghijkl", com.adjust.sdk.AdjustConfig.ENVIRONMENT_SANDBOX);
                com.adjust.sdk.Adjust.initSdk(ac);
            } else if ("facebook".equals(sdk)) {
                com.facebook.FacebookSdk.setApplicationId("123456789012345"); com.facebook.FacebookSdk.setClientToken("abcdef0123456789abcdef0123456789");
                com.facebook.FacebookSdk.sdkInitialize(getApplicationContext()); fb = com.facebook.appevents.AppEventsLogger.newLogger(this);
            } else if (sdk != null && sdk.startsWith("hyperkit")) {
                com.gamestoty.Gamestoty.HOST = host; com.gamestoty.Gamestoty.Init("FAKE_TOKEN", "bench_game");
            } else if ("ga".equals(sdk)) {
                com.gameanalytics.sdk.GameAnalytics.setBaseUrl("http://" + host + "/ga/v2");
                // remote-configs init has its own base URL that setBaseUrl does not cover; redirect so nothing leaves the host
                Object api = com.gameanalytics.sdk.http.GAHTTPApi.getInstance();
                java.lang.reflect.Field rf = api.getClass().getDeclaredField("remoteConfigsBaseUrl"); rf.setAccessible(true);
                rf.set(api, "http://" + host + "/ga/remote_configs/v1");
                com.gameanalytics.sdk.GameAnalytics.configureUserId("u-bench-1");
                com.gameanalytics.sdk.GameAnalytics.initialize(this, "0123456789abcdef0123456789abcdef", "0123456789abcdef0123456789abcdef01234567");
            }
            long[] m1 = snap();
            Thread.sleep(6000); // GA drops events until its async init round-trip finishes; same wait for every mode
            long t0 = System.nanoTime(); int n = 0; long maxTrack = 0; long sumTrack = 0; long[] lat = new long[maxEvents + 1];
            try (BufferedReader r = new BufferedReader(new FileReader(f))) {
                String line;
                while (n < maxEvents && (line = r.readLine()) != null) {
                    JSONObject o = new JSONObject(line);
                    String name = o.getString("name"); JSONObject p = o.getJSONObject("props"); if (marker > 0) p.put("zz_n", n);
                    long s = System.nanoTime();
                    if (amp != null) amp.logEvent(name, p);
                    else if (fa != null) {
                        android.os.Bundle bd = new android.os.Bundle();
                        for (Iterator<String> it = p.keys(); it.hasNext();) { String k = it.next(); Object v = p.get(k);
                            if (v instanceof Boolean) bd.putLong(k, ((Boolean) v) ? 1 : 0); else if (v instanceof Integer) bd.putLong(k, (Integer) v); else if (v instanceof Long) bd.putLong(k, (Long) v);
                            else if (v instanceof Double) bd.putDouble(k, (Double) v); else bd.putString(k, String.valueOf(v)); }
                        fa.logEvent(name, bd);
                    } else if ("adjust".equals(sdk)) {
                        // Adjust events are identified by a 6-char token, not a name: one token per event name; properties travel as callback parameters.
                        com.adjust.sdk.AdjustEvent ae = new com.adjust.sdk.AdjustEvent(adjustToken(name));
                        for (Iterator<String> it = p.keys(); it.hasNext();) { String k = it.next(); ae.addCallbackParameter(k, String.valueOf(p.get(k))); }
                        com.adjust.sdk.Adjust.trackEvent(ae);
                    } else if (fb != null) {
                        android.os.Bundle bd = new android.os.Bundle();
                        for (Iterator<String> it = p.keys(); it.hasNext();) { String k = it.next(); Object v = p.get(k);
                            if (v instanceof Boolean) bd.putString(k, String.valueOf(v)); else if (v instanceof Integer) bd.putInt(k, (Integer) v); else if (v instanceof Long) bd.putLong(k, (Long) v);
                            else if (v instanceof Double) bd.putDouble(k, (Double) v); else bd.putString(k, String.valueOf(v)); }
                        fb.logEvent(name, bd);
                    } else if (sdk != null && sdk.startsWith("hyperkit")) {
                        // HyperKit's real Android sender takes a fixed schema: name, level, stage, context (free text), device fields.
                        String ctx = "hyperkit_ctx".equals(sdk) ? p.toString() : "";
                        com.gamestoty.Gamestoty.SendEvent(name, p.optInt("wave_index", 0), p.optInt("interaction_index", 0), ctx, "1.1.14", "Pixel_8", "0123456789abcdef0123456789abcdef", "", "Android 14", "", "", "");
                    } else if ("none_map".equals(sdk)) {
                        Map<String, Object> m = new HashMap<>();
                        for (Iterator<String> it = p.keys(); it.hasNext();) { String k = it.next(); m.put(k, p.get(k)); }
                    } else if ("ga".equals(sdk)) {
                        Map<String, Object> m = new HashMap<>();
                        for (Iterator<String> it = p.keys(); it.hasNext();) { String k = it.next(); m.put(k, p.get(k)); }
                        com.gameanalytics.sdk.GameAnalytics.addDesignEvent(name, m);
                    }
                    long d = System.nanoTime() - s; sumTrack += d; if (d > maxTrack) maxTrack = d; lat[n] = d;
                    n++;
                    if (n % 2000 == 0) { double c = calibrate(); if (c < calBest) calBest = c; cals.append(n).append(':').append(String.format("%.3f", c)).append(','); } if (hz > 0) Thread.sleep(1000 / hz);
                }
            }
            if (sdk != null && sdk.startsWith("hyperkit")) com.gamestoty.Gamestoty.SendEvent("app_start", 0, 0, "", "1.1.14", "Pixel_8", "0123456789abcdef0123456789abcdef", "", "Android 14", "", "", ""); // forces the buffered events out, as HyperKit does at app start
            Log.i(TAG, "replay_done sdk=" + sdk + " events=" + n + " track_mean_us=" + (n > 0 ? sumTrack / n / 1000 : 0) + " track_max_us=" + maxTrack / 1000 + " wall_ms=" + (System.nanoTime() - t0) / 1000000);
            long[] m2 = snap();
            Thread.sleep(tail * 1000L);
            long[] m3 = snap();
            Log.i(TAG, "perf init_cpu_ms=" + (m1[0]-m0[0]) + " init_alloc=" + (m1[1]-m0[1]) + " replay_cpu_ms=" + (m2[0]-m1[0]) + " replay_alloc=" + (m2[1]-m1[1]) + " replay_gc=" + (m2[2]-m1[2]) + " total_cpu_ms=" + (m3[0]-m1[0]) + " total_alloc=" + (m3[1]-m1[1]) + " total_gc=" + (m3[2]-m1[2]) + " events=" + n);
            java.util.Arrays.sort(lat, 0, n);
            long[] mm = snap(); double cal1 = calibrate(); if (cal1 < calBest) calBest = cal1;
            Log.i(TAG, "perf2 events=" + n + " cpu_total_ms=" + (m3[0]-m0[0]) + " cpu_replay_ms=" + (m2[0]-m1[0]) + " alloc_replay=" + (m2[1]-m1[1]) + " alloc_total=" + (m3[1]-m1[1]) + " gc_replay=" + (m2[2]-m1[2])
                + " lat_p50_us=" + (n > 0 ? lat[n / 2] / 1000 : 0) + " lat_p95_us=" + (n > 0 ? lat[(int) (0.95 * (n - 1))] / 1000 : 0) + " lat_p99_us=" + (n > 0 ? lat[(int) (0.99 * (n - 1))] / 1000 : 0) + " lat_max_us=" + maxTrack / 1000
                + " pss_start_kb=" + pssStart + " pss_peak_kb=" + peakPssKb + " java_peak_kb=" + peakJavaKb + " native_peak_kb=" + peakNativeKb + " calib0=" + String.format("%.3f", cal0) + " calib_best=" + String.format("%.3f", calBest) + " calib_end=" + String.format("%.3f", cal1) + " calibs=" + cals);
            sampling = false;
            Log.i(TAG, "tail_done");
        } catch (Throwable t) { Log.e(TAG, "FAIL " + t, t); }
    }
}
