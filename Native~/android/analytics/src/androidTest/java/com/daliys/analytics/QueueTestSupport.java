// Helpers of the Android queue device tests: record frames, readOldest decoding, legacy databases and assertions.
package com.daliys.analytics;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;

/** Shared helpers of {@link AnalyticsQueueInstrumentationTest}. */
final class QueueTestSupport {
    private QueueTestSupport() { }

    static long longOf(String text) { return text == null || text.isEmpty() ? 0L : Long.parseLong(text); }

    static String id(int n) {
        return String.format("%08x-aaaa-4aaa-8aaa-%012x", n, n);
    }

    /** A binary event record the way the C# writer lays out its fixed header (format, event id, session id); the queue reads only the id. */
    static byte[] record(String eventId, int tail) {
        byte[] record = new byte[33 + tail];
        record[0] = 1;
        uuidBytes(eventId, record, 1);
        uuidBytes("9be11ebf-e4f3-4696-9a47-7784061e15aa", record, 17);
        for (int i = 0; i < tail; i++) record[33 + i] = (byte) i;
        return record;
    }

    static void uuidBytes(String uuid, byte[] destination, int offset) {
        String hex = uuid.replace("-", "");
        for (int i = 0; i < 16; i++) destination[offset + i] = (byte) Integer.parseInt(hex.substring(i * 2, i * 2 + 2), 16);
    }

    static byte[] frames(int tail, String... eventIds) {
        java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
        for (String eventId : eventIds) {
            byte[] record = record(eventId, tail);
            out.write(record.length >>> 24); out.write(record.length >>> 16); out.write(record.length >>> 8); out.write(record.length);
            out.write(record, 0, record.length);
        }
        return out.toByteArray();
    }

    static int enqueue(AnalyticsQueue queue, int eventLimit, long byteLimit, long maxAge, String... eventIds) {
        queue.setLimits(eventLimit, byteLimit, maxAge);
        return queue.enqueueRecords(frames(8, eventIds), eventIds.length);
    }

    /** readOldest decoded to the shape the assertions use: {event_id, sequence, format} (format 0 rows are the stored JSON minus install_id). */
    static String pendingJson(AnalyticsQueue queue, int max) throws Exception {
        byte[] data = queue.readOldest(max);
        java.nio.ByteBuffer buffer = java.nio.ByteBuffer.wrap(data);
        int count = buffer.getInt();
        JSONArray rows = new JSONArray();
        for (int i = 0; i < count; i++) {
            int format = buffer.get();
            long sequence = buffer.getLong();
            byte[] payload = new byte[buffer.getInt()];
            buffer.get(payload);
            JSONObject row;
            if (format == 0) {
                row = new JSONObject(new String(payload, java.nio.charset.StandardCharsets.UTF_8));
                row.remove("install_id");
            } else {
                StringBuilder id = new StringBuilder();
                for (int b = 0; b < 16; b++) {
                    if (b == 4 || b == 6 || b == 8 || b == 10) id.append('-');
                    id.append(String.format("%02x", payload[1 + b] & 0xff));
                }
                row = new JSONObject().put("event_id", id.toString());
            }
            row.put("sequence", sequence).put("format", format);
            rows.put(row);
        }
        return rows.toString();
    }

    static File databaseFile(Context context) {
        return new File(context.getNoBackupFilesDir(), AnalyticsQueue.DATABASE_NAME);
    }

    static void deleteDatabaseFiles(File databaseFile) {
        databaseFile.delete();
        new File(databaseFile.getAbsolutePath() + "-wal").delete();
        new File(databaseFile.getAbsolutePath() + "-shm").delete();
    }

    static void createVersionOneDatabase(File databaseFile) throws Exception {
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

    static void putMetadata(SQLiteDatabase database, String key, String value) {
        ContentValues row = new ContentValues();
        row.put("key", key);
        row.put("value", value);
        database.insertOrThrow("metadata", null, row);
    }

    static boolean hasAttemptCountColumn(File databaseFile) {
        try (SQLiteDatabase database = SQLiteDatabase.openDatabase(databaseFile.getAbsolutePath(), null, SQLiteDatabase.OPEN_READONLY);
             Cursor columns = database.rawQuery("PRAGMA table_info(pending_events)", null)) {
            while (columns.moveToNext()) {
                if ("attempt_count".equals(columns.getString(columns.getColumnIndexOrThrow("name"))))
                    return true;
            }
            return false;
        }
    }

    static void assertEquals(Object expected, Object actual) {
        if (expected == null ? actual != null : !expected.equals(actual))
            throw new AssertionError("Expected " + expected + " but was " + actual + ".");
    }

    static void assertTrue(boolean condition) {
        if (!condition) throw new AssertionError("Expected true.");
    }

    static void assertNotEquals(Object unexpected, Object actual) {
        if (unexpected == null ? actual == null : unexpected.equals(actual))
            throw new AssertionError("Did not expect " + actual + ".");
    }
}
