package com.gamestoty;

import android.util.Log;
import android.content.Context;
import android.content.ContentResolver;
import android.provider.Settings.Secure;
import android.provider.Settings.SettingNotFoundException;

import com.google.android.gms.ads.identifier.AdvertisingIdClient;
import com.google.android.gms.common.GooglePlayServicesNotAvailableException;
import com.google.android.gms.common.GooglePlayServicesRepairableException;
import com.unity3d.player.UnityPlayer;

import android.os.AsyncTask;
import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Random;
import java.util.TimeZone;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

import com.google.common.util.concurrent.Futures;

public class Gamestoty {

    public static final MediaType JSON = MediaType.get("application/json; charset=utf-8");
    private static final String TAG = "Gamestoty";

    private static String _token;
    private static String _game_id;
    private static String _session_id;
    private static int _event_seq;
    private static JSONArray _eventBuffer;
    private static OkHttpClient _httpClient;
    private static long _time;
    private static long _sendDelay = 5;

    public static String HOST = "10.0.2.2:18431"; public static String IDFA;
    public static boolean CheckIdfa = false;

    static SimpleDateFormat dateFormat = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
    static SimpleDateFormat dateFormatUTC = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");

    public static void Init(String token, String game_id) {
		_time = System.currentTimeMillis();

        _token = token;
        _game_id = game_id;
        _session_id = randomIdString();
        _event_seq = 0;

        _httpClient = new OkHttpClient();
        _eventBuffer = new JSONArray();
    }

    public static void SendEvent(String event, int level, int stage, String context, String app_version, String device, String device_id, String device_idfa, String device_os, String fps, String source, String campaign) {
		if (fps == null || fps.isEmpty()) {
            fps="[]";
        }

        _event_seq++;
        dateFormatUTC.setTimeZone(TimeZone.getTimeZone("GMT"));
        String ts_client = dateFormatUTC.format(new Date());
        String ts_client_local = dateFormat.format(new Date());

        JSONObject eventJson = new JSONObject();
        try {
            eventJson.put("event",event);
			eventJson.put("level",level);
            eventJson.put("stage",stage);
            eventJson.put("context",context);

            eventJson.put("app_ver",app_version);
            eventJson.put("device",device);
            eventJson.put("device_id",device_id);
			eventJson.put("device_idfa",device_idfa);
            eventJson.put("device_os",device_os);

            eventJson.put("ts_client",ts_client);
            eventJson.put("ts_client_local",ts_client_local);
            eventJson.put("event_seq", _event_seq);
            eventJson.put("event_id", randomIdString());
            eventJson.put("sid", _session_id);
			eventJson.put("fps", new JSONArray(fps));
			eventJson.put("source", source);
			eventJson.put("campaign", campaign);
            eventJson.put("test", false);

            if (_eventBuffer == null)
                _eventBuffer = new JSONArray();

            _eventBuffer.put(eventJson);

            long sec = (System.currentTimeMillis() - _time)/1000;

            if (sec >= _sendDelay || event.equals("app_start")) {
                _time = System.currentTimeMillis();

                JSONArray eventArray = new JSONArray();
                eventArray = _eventBuffer;
                _eventBuffer = new JSONArray();

        		Request request = new Request.Builder()
                	.url("http://" + HOST + "/hk/events/" + _game_id)
                	.addHeader("Authorization", "Bearer " + _token)
                	.post(RequestBody.create(JSON,eventArray.toString()))
                	.build();

                if (_httpClient == null)
                    _httpClient = new OkHttpClient();

        		_httpClient.newCall(request).enqueue(new Callback() {
           			@Override public void onFailure(Call call, IOException e) {
                		//Log.i("onFailure", e.toString());
            		}

            		@Override public void onResponse(Call call, Response response) throws IOException {
                		//Log.i("onResponse", response.body().toString());
					}
        		});
			}
        } catch (Exception e) {
            //TODO: handle exception
        }
    }

    private static String randomIdString()
    {
        final String ALLOWED_CHARACTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
        int sizeOfRandomString = 16;

        final Random random = new Random();
        final StringBuilder sb = new StringBuilder(sizeOfRandomString);

        for (int i=0;i<sizeOfRandomString;++i)
            sb.append(ALLOWED_CHARACTERS.charAt(random.nextInt(ALLOWED_CHARACTERS.length())));

        return sb.toString();
    }

   private static void determineAdvertisingInfo() {
        CheckIdfa = true;
        AsyncTask.execute(new Runnable() {
            @Override
            public void run() {
                final Context ctx = UnityPlayer.currentActivity.getApplicationContext();
                try {
                    AdvertisingIdClient.Info advertisingIdInfo = AdvertisingIdClient.getAdvertisingIdInfo(ctx);
                    // You should check this in case the user disabled it from settings
                    if (!advertisingIdInfo.isLimitAdTrackingEnabled()) {
                        IDFA = advertisingIdInfo.getId();
                        CheckIdfa = false;
                        // getUserAttributes(id);
                    } else {
                        CheckIdfa = false;
                        //If you stored the id you should remove it
                    }
                } catch (IOException | GooglePlayServicesNotAvailableException | GooglePlayServicesRepairableException e) {
                    Log.e(TAG, "Google IDFA failure", e);

                    //Amazon IDFA
                    try {
                        final ContentResolver cr = ctx.getContentResolver();
                        final boolean limitAdTracking = (Secure.getInt(cr, "limit_ad_tracking") == 0) ? false : true;
                        if (!limitAdTracking) {
                            IDFA = Secure.getString(cr, "advertising_id");
                        } else {
                            Log.w(TAG, "Amazon AD tracking is limited");
                        }
                        CheckIdfa = false;
                    } catch (SettingNotFoundException ex) {
                        Log.e(TAG, "Amazon IDFA failure", ex);
                        CheckIdfa = false;
                    }
                }

                Log.d(TAG, "IDFA : " + IDFA);
            }
        });
    }
}