package com.daliys.analytics;

import android.content.Context;
import android.content.ContentValues;
import android.app.Activity;
import android.app.Instrumentation;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.os.Bundle;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.io.File;
import java.io.FileOutputStream;

/** Dependency-free device-level contract runner for the owned SQLite queue. */
public final class AnalyticsQueueInstrumentationTest extends Instrumentation {
    private static final int EVENT_LIMIT = 10;
    private static final long BYTE_LIMIT = 1024L * 1024L;
    private static final long MAX_AGE_MILLIS = 24L * 60L * 60L * 1000L;

    @Override public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override public void onStart() {
        super.onStart();
        Bundle result = new Bundle();
        try {
            testEventsAndIdentitySurviveQueueReopen(getTargetContext());
            testQueueEvictsTheOldestRowsWhenEventLimitIsExceeded(getTargetContext());
            testCorruptDatabaseIsResetWithNewIdentity(getTargetContext());
            testVersionOneDatabaseUpgradesWithoutDroppingQueuedEvent(getTargetContext());
            testResetIdentityKeepsQueuedEventsAndAdvancesSequence(getTargetContext());
            result.putString(REPORT_KEY_STREAMRESULT, "U1 device queue tests passed.\n");
            finish(Activity.RESULT_OK, result);
        } catch (Throwable failure) {
            StringWriter trace = new StringWriter();
            failure.printStackTrace(new PrintWriter(trace));
            result.putString(REPORT_KEY_STREAMRESULT, "U1 device queue tests failed:\n" + trace + "\n");
            finish(Activity.RESULT_CANCELED, result);
        }
    }

    private static void testEventsAndIdentitySurviveQueueReopen(Context context) throws Exception {
        AnalyticsQueue queue = new AnalyticsQueue(context);
        queue.clearAllPendingEvents();
        String eventId = "1a23bc45-6789-4def-8123-456789abcdef";
        QueueResult beforeClose = queue.enqueueBatch(events(eventId), EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS);
        String installationId = beforeClose.getInstallationId();
        String credential = beforeClose.getInstallationCredential();
        queue.close();
        queue = new AnalyticsQueue(context);

        QueueResult reopened = queue.getState();
        JSONArray pending = new JSONArray(queue.readOldestBatch(EVENT_LIMIT));

        assertEquals(installationId, reopened.getInstallationId());
        assertEquals(credential, reopened.getInstallationCredential());
        assertEquals(1, pending.length());
        assertEquals(eventId, pending.getJSONObject(0).getString("event_id"));
        queue.close();
    }

    private static void testQueueEvictsTheOldestRowsWhenEventLimitIsExceeded(Context context) throws Exception {
        AnalyticsQueue queue = new AnalyticsQueue(context);
        queue.clearAllPendingEvents();
        String oldestId = "11111111-1111-4111-8111-111111111111";
        String middleId = "22222222-2222-4222-8222-222222222222";
        String newestId = "33333333-3333-4333-8333-333333333333";

        QueueResult result = queue.enqueueBatch(events(oldestId, middleId, newestId), 2, BYTE_LIMIT, MAX_AGE_MILLIS);
        JSONArray pending = new JSONArray(queue.readOldestBatch(EVENT_LIMIT));

        assertEquals(3, result.getInsertedCount());
        assertEquals(1, result.getEvictedCount());
        assertEquals(2, pending.length());
        assertEquals(middleId, pending.getJSONObject(0).getString("event_id"));
        assertEquals(newestId, pending.getJSONObject(1).getString("event_id"));
        long middleSequence = pending.getJSONObject(0).getLong("sequence");
        assertEquals(middleSequence + 1L, pending.getJSONObject(1).getLong("sequence"));
        queue.close();
    }

    private static void testCorruptDatabaseIsResetWithNewIdentity(Context context) throws Exception {
        AnalyticsQueue queue = new AnalyticsQueue(context);
        queue.clearAllPendingEvents();
        QueueResult beforeCorruption = queue.enqueueBatch(events("44444444-4444-4444-8444-444444444444"), EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS);
        File databaseFile = databaseFile(context);
        queue.close();
        deleteDatabaseFiles(databaseFile);
        try (FileOutputStream corrupt = new FileOutputStream(databaseFile)) {
            corrupt.write(new byte[] {0x42, 0x41, 0x44, 0x21});
        }

        queue = new AnalyticsQueue(context);
        QueueResult recovered = queue.getState();

        assertNotEquals(beforeCorruption.getInstallationId(), recovered.getInstallationId());
        assertEquals(0, new JSONArray(queue.readOldestBatch(EVENT_LIMIT)).length());
        queue.close();
    }

    private static void testVersionOneDatabaseUpgradesWithoutDroppingQueuedEvent(Context context) throws Exception {
        File databaseFile = databaseFile(context);
        deleteDatabaseFiles(databaseFile);
        createVersionOneDatabase(databaseFile);

        AnalyticsQueue queue = new AnalyticsQueue(context);
        JSONArray pending = new JSONArray(queue.readOldestBatch(EVENT_LIMIT));

        assertEquals(1, pending.length());
        assertEquals("55555555-5555-4555-8555-555555555555", pending.getJSONObject(0).getString("event_id"));
        assertEquals(false, pending.getJSONObject(0).has("install_id"));
        assertEquals(true, hasAttemptCountColumn(databaseFile));
        queue.close();
    }

    private static void testResetIdentityKeepsQueuedEventsAndAdvancesSequence(Context context) throws Exception {
        AnalyticsQueue queue = new AnalyticsQueue(context);
        queue.clearAllPendingEvents();
        QueueResult beforeReset = queue.enqueueBatch(events("66666666-6666-4666-8666-666666666666"), EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS);
        long firstSequence = new JSONArray(queue.readOldestBatch(EVENT_LIMIT)).getJSONObject(0).getLong("sequence");

        QueueResult afterReset = queue.resetIdentity();
        queue.enqueueBatch(events("77777777-7777-4777-8777-777777777777"), EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS);
        JSONArray pending = new JSONArray(queue.readOldestBatch(EVENT_LIMIT));

        assertNotEquals(beforeReset.getInstallationId(), afterReset.getInstallationId());
        assertEquals(2, pending.length());
        assertEquals(firstSequence + 1L, pending.getJSONObject(1).getLong("sequence"));
        queue.close();
    }

    private static String events(String... eventIds) throws Exception {
        JSONArray events = new JSONArray();
        for (String eventId : eventIds) {
            JSONObject event = new JSONObject();
            event.put("event_id", eventId);
            event.put("session_id", "9be11ebf-e4f3-4696-9a47-7784061e15aa");
            event.put("name", "level_start");
            event.put("occurred_at_client", "2026-07-18T18:00:00.0000000+00:00");
            event.put("properties", new JSONObject().put("house_id", "rome_01"));
            events.put(event);
        }
        return events.toString();
    }

    private static File databaseFile(Context context) {
        return new File(context.getNoBackupFilesDir(), AnalyticsQueue.DATABASE_NAME);
    }

    private static void deleteDatabaseFiles(File databaseFile) {
        databaseFile.delete();
        new File(databaseFile.getAbsolutePath() + "-wal").delete();
        new File(databaseFile.getAbsolutePath() + "-shm").delete();
    }

    private static void createVersionOneDatabase(File databaseFile) throws Exception {
        SQLiteDatabase legacy = SQLiteDatabase.openOrCreateDatabase(databaseFile, null);
        legacy.execSQL("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)");
        legacy.execSQL("CREATE TABLE pending_events (row_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE, install_id TEXT NOT NULL, session_id TEXT NOT NULL, sequence INTEGER NOT NULL, session_elapsed_ms INTEGER NOT NULL, name TEXT NOT NULL, occurred_at_client TEXT NOT NULL, properties_json TEXT NOT NULL, properties_bytes INTEGER NOT NULL, payload_json TEXT NOT NULL, created_at_epoch_ms INTEGER NOT NULL)");
        legacy.execSQL("CREATE INDEX pending_events_created_at ON pending_events(created_at_epoch_ms)");
        putMetadata(legacy, "install_id", "12121212-1212-4121-8121-121212121212");
        putMetadata(legacy, "installation_credential", "legacy_credential");
        putMetadata(legacy, "next_sequence", "8");
        putMetadata(legacy, "registered", "false");

        String eventId = "55555555-5555-4555-8555-555555555555";
        JSONObject payload = new JSONObject();
        payload.put("event_id", eventId);
        payload.put("install_id", "12121212-1212-4121-8121-121212121212");
        payload.put("session_id", "9be11ebf-e4f3-4696-9a47-7784061e15aa");
        payload.put("sequence", 7);
        payload.put("name", "level_start");
        payload.put("occurred_at_client", "2026-07-18T18:00:00.0000000+00:00");
        payload.put("properties", new JSONObject().put("house_id", "rome_01"));
        ContentValues row = new ContentValues();
        row.put("event_id", eventId);
        row.put("install_id", "12121212-1212-4121-8121-121212121212");
        row.put("session_id", "9be11ebf-e4f3-4696-9a47-7784061e15aa");
        row.put("sequence", 7L);
        row.put("session_elapsed_ms", 0L);
        row.put("name", "level_start");
        row.put("occurred_at_client", "2026-07-18T18:00:00.0000000+00:00");
        row.put("properties_json", "{\"house_id\":\"rome_01\"}");
        row.put("properties_bytes", 21);
        row.put("payload_json", payload.toString());
        row.put("created_at_epoch_ms", 1L);
        legacy.insertOrThrow("pending_events", null, row);
        legacy.setVersion(1);
        legacy.close();
    }

    private static void putMetadata(SQLiteDatabase database, String key, String value) {
        ContentValues row = new ContentValues();
        row.put("key", key);
        row.put("value", value);
        database.insertOrThrow("metadata", null, row);
    }

    private static boolean hasAttemptCountColumn(File databaseFile) {
        try (SQLiteDatabase database = SQLiteDatabase.openDatabase(databaseFile.getAbsolutePath(), null, SQLiteDatabase.OPEN_READONLY);
             Cursor columns = database.rawQuery("PRAGMA table_info(pending_events)", null)) {
            while (columns.moveToNext()) {
                if ("attempt_count".equals(columns.getString(columns.getColumnIndexOrThrow("name"))))
                    return true;
            }
            return false;
        }
    }

    private static void assertEquals(Object expected, Object actual) {
        if (expected == null ? actual != null : !expected.equals(actual))
            throw new AssertionError("Expected " + expected + " but was " + actual + ".");
    }

    private static void assertNotEquals(Object unexpected, Object actual) {
        if (unexpected == null ? actual == null : unexpected.equals(actual))
            throw new AssertionError("Did not expect " + actual + ".");
    }
}
