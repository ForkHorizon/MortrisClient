package bench;

import android.content.Context;
import android.os.Bundle;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;
import org.json.JSONObject;

/** One adapter, one SDK per process. The Unity probe hands over (name, flat JSON props); every mode parses the JSON the same way, so mode "noop" is the
 *  baseline (JNI + parse) that the analysis subtracts. Endpoints are redirected to the cleartext collector wherever the SDK allows it. */
public final class CmpAdapter {
    static String sdk = "noop";
    static com.amplitude.api.AmplitudeClient amp;
    static com.amplitude.android.Amplitude ampK;
    static com.google.firebase.analytics.FirebaseAnalytics fa;
    static com.facebook.appevents.AppEventsLogger fb;
    static com.mixpanel.android.mpmetrics.MixpanelAPI mp;
    static final Map<String, String> TOKENS = new HashMap<>();
    static long events;

    static String adjustToken(String name) {
        String t = TOKENS.get(name);
        if (t == null) { t = String.format("%06x", TOKENS.size() + 0x100001).substring(0, 6).replace('0', 'a'); TOKENS.put(name, t); }
        return t;
    }

    public static String init(Context ctx, String which, String host, String opts) {
        sdk = which;
        try {
            JSONObject o = opts == null || opts.isEmpty() ? new JSONObject() : new JSONObject(opts);
            if ("amplitude".equals(sdk)) {
                amp = com.amplitude.api.Amplitude.getInstance();
                amp.initialize(ctx, "FAKE_API_KEY_0000000000000000").setServerUrl("http://" + host + "/amp");
                if (o.has("threshold")) amp.setEventUploadThreshold(o.getInt("threshold"));
                if (o.has("period_ms")) amp.setEventUploadPeriodMillis(o.getInt("period_ms"));
                if (o.has("batch")) amp.setEventUploadMaxBatchSize(o.getInt("batch"));
                amp.setUserId("u-bench-1");
            } else if ("amplitude_kotlin".equals(sdk)) {
                com.amplitude.android.Configuration c = new com.amplitude.android.Configuration("FAKE_API_KEY_0000000000000000", ctx.getApplicationContext());
                c.setServerUrl("http://" + host + "/ampk");
                c.setUseBatch(false);
                if (o.has("flush_queue_size")) c.setFlushQueueSize(o.getInt("flush_queue_size"));
                if (o.has("flush_interval_ms")) c.setFlushIntervalMillis(o.getInt("flush_interval_ms"));
                ampK = new com.amplitude.android.Amplitude(c); ampK.setUserId("u-bench-1");
            } else if ("firebase".equals(sdk)) {
                if (com.google.firebase.FirebaseApp.getApps(ctx).isEmpty())
                    com.google.firebase.FirebaseApp.initializeApp(ctx, new com.google.firebase.FirebaseOptions.Builder()
                        .setApplicationId("1:123456789012:android:0123456789abcdef").setApiKey("AIzaSyFAKE0000000000000000000000000000").setProjectId("bench-fake").build());
                fa = com.google.firebase.analytics.FirebaseAnalytics.getInstance(ctx);
                fa.setAnalyticsCollectionEnabled(true);
            } else if ("adjust".equals(sdk)) {
                com.adjust.sdk.Adjust.initSdk(new com.adjust.sdk.AdjustConfig(ctx, "abcdefghijkl", com.adjust.sdk.AdjustConfig.ENVIRONMENT_SANDBOX));
            } else if ("facebook".equals(sdk)) {
                com.facebook.FacebookSdk.setApplicationId("123456789012345"); com.facebook.FacebookSdk.setClientToken("abcdef0123456789abcdef0123456789");
                com.facebook.FacebookSdk.sdkInitialize(ctx.getApplicationContext()); fb = com.facebook.appevents.AppEventsLogger.newLogger(ctx);
            } else if ("hyperkit_core".equals(sdk) || "hyperkit_ctx".equals(sdk)) {
                com.gamestoty.Gamestoty.HOST = host; com.gamestoty.Gamestoty.Init("FAKE_TOKEN", "bench_game");
            } else if ("ga".equals(sdk)) {
                com.gameanalytics.sdk.GameAnalytics.setBaseUrl("http://" + host + "/ga/v2");
                Object api = com.gameanalytics.sdk.http.GAHTTPApi.getInstance();
                java.lang.reflect.Field rf = api.getClass().getDeclaredField("remoteConfigsBaseUrl"); rf.setAccessible(true);
                rf.set(api, "http://" + host + "/ga/remote_configs/v1");
                com.gameanalytics.sdk.GameAnalytics.configureUserId("u-bench-1");
                com.gameanalytics.sdk.GameAnalytics.initialize(ctx instanceof android.app.Activity ? (android.app.Activity) ctx : null, "0123456789abcdef0123456789abcdef", "0123456789abcdef0123456789abcdef01234567");
            } else if ("mixpanel".equals(sdk)) {
                mp = com.mixpanel.android.mpmetrics.MixpanelAPI.getInstance(ctx, "0123456789abcdef0123456789abcdef", false);
                mp.setServerURL("http://" + host + "/mp"); mp.identify("u-bench-1");
            }
            return "ok";
        } catch (Throwable t) { android.util.Log.e("CMP", "init " + sdk, t); return "FAIL " + t; }
    }

    public static void track(String name, String json) {
        try {
            events++;
            JSONObject p = new JSONObject(json);
            switch (sdk) {
                case "amplitude": amp.logEvent(name, p); break;
                case "amplitude_kotlin": { Map<String, Object> m = map(p); ampK.track(name, m); break; }
                case "firebase": { Bundle b = new Bundle();
                    for (Iterator<String> it = p.keys(); it.hasNext();) { String k = it.next(); Object v = p.get(k);
                        if (v instanceof Boolean) b.putLong(k, ((Boolean) v) ? 1 : 0); else if (v instanceof Integer) b.putLong(k, (Integer) v); else if (v instanceof Long) b.putLong(k, (Long) v);
                        else if (v instanceof Double) b.putDouble(k, (Double) v); else b.putString(k, String.valueOf(v)); }
                    fa.logEvent(name, b); break; }
                case "facebook": { Bundle b = new Bundle();
                    for (Iterator<String> it = p.keys(); it.hasNext();) { String k = it.next(); Object v = p.get(k);
                        if (v instanceof Boolean) b.putString(k, String.valueOf(v)); else if (v instanceof Integer) b.putInt(k, (Integer) v); else if (v instanceof Long) b.putLong(k, (Long) v);
                        else if (v instanceof Double) b.putDouble(k, (Double) v); else b.putString(k, String.valueOf(v)); }
                    fb.logEvent(name, b); break; }
                case "adjust": { com.adjust.sdk.AdjustEvent ae = new com.adjust.sdk.AdjustEvent(adjustToken(name));
                    for (Iterator<String> it = p.keys(); it.hasNext();) { String k = it.next(); ae.addCallbackParameter(k, String.valueOf(p.get(k))); }
                    com.adjust.sdk.Adjust.trackEvent(ae); break; }
                case "hyperkit_core": case "hyperkit_ctx": {
                    String ctx = "hyperkit_ctx".equals(sdk) ? p.toString() : "";
                    com.gamestoty.Gamestoty.SendEvent(name, p.optInt("wave_index", 0), p.optInt("interaction_index", 0), ctx, "1.1.14", "Pixel_8", "0123456789abcdef0123456789abcdef", "", "Android 14", "", "", ""); break; }
                case "ga": com.gameanalytics.sdk.GameAnalytics.addDesignEvent(name, map(p)); break;
                case "mixpanel": mp.track(name, p); break;
                default: map(p); break; // noop: parse only
            }
        } catch (Throwable t) { android.util.Log.e("CMP", "track " + sdk, t); }
    }

    static Map<String, Object> map(JSONObject p) throws Exception {
        Map<String, Object> m = new HashMap<>();
        for (Iterator<String> it = p.keys(); it.hasNext();) { String k = it.next(); m.put(k, p.get(k)); }
        return m;
    }

    /** What an app does when it goes to the background or the player finishes: ask the SDK to push what it holds. */
    public static void flush() {
        try {
            if (amp != null) amp.uploadEvents();
            if (ampK != null) ampK.flush();
            if (mp != null) mp.flush();
            if (sdk.startsWith("hyperkit")) com.gamestoty.Gamestoty.SendEvent("app_start", 0, 0, "", "1.1.14", "Pixel_8", "0123456789abcdef0123456789abcdef", "", "Android 14", "", "", "");
        } catch (Throwable t) { android.util.Log.e("CMP", "flush", t); }
    }

    public static long count() { return events; }
}
