package com.daliys.analytics;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import android.util.Base64;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.Closeable;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.UUID;

/**
 * Single-owner durable queue for the Unity SDK. Callers serialize access through
 * the C# persistence worker; methods are synchronized as a defensive boundary.
 */
public final class AnalyticsQueue implements Closeable {
    static final String DATABASE_NAME = "daliys_analytics.db";
    private static final int DATABASE_VERSION = 2;
    private static final String META_INSTALL_ID = "install_id";
    private static final String META_CREDENTIAL = "installation_credential";
    private static final String META_NEXT_SEQUENCE = "next_sequence";

    private final Context context;
    private final File databaseFile;
    private QueueOpenHelper helper;
    private SQLiteDatabase database;
    private final SecureRandom secureRandom = new SecureRandom();

    public AnalyticsQueue(Context context) {
        this.context = context.getApplicationContext();
        File directory = context.getNoBackupFilesDir();
        databaseFile = new File(directory, DATABASE_NAME);
        helper = new QueueOpenHelper(this.context, databaseFile.getAbsolutePath());
        database = openDatabaseWithRecovery();
        ensureIdentity();
    }

    public synchronized QueueResult getState() {
        Identity identity = ensureIdentity();
        return result(identity, 0, 0, 0);
    }

    /** Replaces only an invalid credential/identity pair; queued events remain durable. */
    public synchronized QueueResult resetIdentity() {
        Identity identity;
        database.beginTransaction();
        try {
            long nextSequence = android.database.DatabaseUtils.longForQuery(database,
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM pending_events", null);
            database.delete("metadata", null, null);
            identity = newIdentity(nextSequence);
            ContentValues eventIdentity = new ContentValues();
            eventIdentity.put("install_id", identity.installationId);
            database.update("pending_events", eventIdentity, null, null);
            database.setTransactionSuccessful();
        } finally {
            database.endTransaction();
        }
        return result(identity, 0, 0, 0);
    }

    /** Inserts a JSON array of fully validated event envelopes in one transaction. */
    public synchronized QueueResult enqueueBatch(String eventsJson, int eventLimit,
                                                  long byteLimit, long maxAgeMillis) throws JSONException {
        if (eventLimit <= 0 || byteLimit <= 0 || maxAgeMillis <= 0)
            throw new IllegalArgumentException("Queue limits must be positive.");

        JSONArray events = new JSONArray(eventsJson);
        Identity identity = ensureIdentity();
        int inserted = 0;
        int evicted;
        int expired;
        database.beginTransaction();
        try {
            long nextSequence = Long.parseLong(requireMetadata(META_NEXT_SEQUENCE));
            for (int index = 0; index < events.length(); index++) {
                JSONObject event = events.getJSONObject(index);
                ContentValues row = toRow(event, identity.installationId, nextSequence);
                long rowId = database.insertWithOnConflict("pending_events", null, row,
                        SQLiteDatabase.CONFLICT_IGNORE);
                if (rowId != -1L) {
                    inserted++;
                    nextSequence++;
                }
            }
            putMetadata(META_NEXT_SEQUENCE, Long.toString(nextSequence));
            expired = deleteExpired(System.currentTimeMillis() - maxAgeMillis);
            evicted = enforceBounds(eventLimit, byteLimit);
            database.setTransactionSuccessful();
        } finally {
            database.endTransaction();
        }
        return result(identity, inserted, evicted, expired);
    }

    /** Returns a compact JSON array of oldest-first payloads for the C# uploader. */
    public synchronized String readOldestBatch(int maxEvents) throws JSONException {
        if (maxEvents <= 0) throw new IllegalArgumentException("maxEvents must be positive.");
        JSONArray batch = new JSONArray();
        try (Cursor cursor = database.query("pending_events", new String[]{"payload_json"}, null,
                null, null, null, "row_id ASC", Integer.toString(maxEvents))) {
            while (cursor.moveToNext()) {
                JSONObject payload = new JSONObject(cursor.getString(0));
                payload.remove("install_id"); // Compatibility with queues written before contract v1.
                batch.put(payload);
            }
        }
        return batch.toString();
    }

    /** Deletes only IDs already validated by the C# acknowledgement parser. */
    public synchronized int deleteAcknowledged(String eventIdsJson) throws JSONException {
        JSONArray ids = new JSONArray(eventIdsJson);
        int deleted = 0;
        database.beginTransaction();
        try {
            for (int index = 0; index < ids.length(); index++)
                deleted += database.delete("pending_events", "event_id = ?", new String[]{ids.getString(index)});
            database.setTransactionSuccessful();
        } finally {
            database.endTransaction();
        }
        return deleted;
    }

    /** Removes every durable event when collection is revoked with clear-pending enabled. */
    public synchronized void clearAllPendingEvents() {
        database.delete("pending_events", null, null);
    }

    @Override public synchronized void close() {
        database.close();
        helper.close();
    }

    private SQLiteDatabase openDatabaseWithRecovery() {
        try {
            return openDatabase();
        } catch (android.database.sqlite.SQLiteException originalFailure) {
            helper.close();
            deleteDatabaseFiles();
            helper = new QueueOpenHelper(context, databaseFile.getAbsolutePath());
            try {
                return openDatabase();
            } catch (android.database.sqlite.SQLiteException recoveryFailure) {
                recoveryFailure.addSuppressed(originalFailure);
                throw recoveryFailure;
            }
        }
    }

    private SQLiteDatabase openDatabase() {
        SQLiteDatabase opened = helper.getWritableDatabase();
        opened.enableWriteAheadLogging();
        return opened;
    }

    private void deleteDatabaseFiles() {
        deleteIfPresent(databaseFile);
        deleteIfPresent(new File(databaseFile.getAbsolutePath() + "-wal"));
        deleteIfPresent(new File(databaseFile.getAbsolutePath() + "-shm"));
    }

    private static void deleteIfPresent(File file) {
        if (file.exists() && !file.delete())
            throw new IllegalStateException("Could not delete corrupt analytics database file: " + file);
    }

    private ContentValues toRow(JSONObject event, String installId, long sequence) throws JSONException {
        String eventId = requireUuid(event, "event_id");
        String sessionId = requireUuid(event, "session_id");
        String name = event.getString("name");
        String occurredAt = event.getString("occurred_at_client");
        JSONObject payload = new JSONObject(event.toString());
        payload.put("sequence", sequence);
        JSONObject properties = payload.optJSONObject("properties");
        String propertiesJson = properties == null ? "{}" : properties.toString();

        ContentValues row = new ContentValues();
        row.put("event_id", eventId);
        row.put("install_id", installId);
        row.put("session_id", sessionId);
        row.put("sequence", sequence);
        row.put("session_elapsed_ms", event.optLong("session_elapsed_ms", 0));
        row.put("name", name);
        row.put("occurred_at_client", occurredAt);
        row.put("properties_json", propertiesJson);
        row.put("properties_bytes", propertiesJson.getBytes(StandardCharsets.UTF_8).length);
        row.put("payload_json", payload.toString());
        row.put("created_at_epoch_ms", System.currentTimeMillis());
        return row;
    }

    private Identity ensureIdentity() {
        database.beginTransaction();
        try {
            String installId = getMetadata(META_INSTALL_ID);
            String credential = getMetadata(META_CREDENTIAL);
            if (!isUuid(installId) || credential == null || credential.isEmpty()) {
                database.delete("pending_events", null, null);
                database.delete("metadata", null, null);
                Identity identity = newIdentity(1);
                installId = identity.installationId;
                credential = identity.credential;
            }
            database.setTransactionSuccessful();
            return new Identity(installId, credential);
        } finally {
            database.endTransaction();
        }
    }

    private Identity newIdentity(long nextSequence) {
        String installId = UUID.randomUUID().toString();
        byte[] credentialBytes = new byte[32];
        secureRandom.nextBytes(credentialBytes);
        String credential = Base64.encodeToString(credentialBytes,
                Base64.URL_SAFE | Base64.NO_PADDING | Base64.NO_WRAP);
        putMetadata(META_INSTALL_ID, installId);
        putMetadata(META_CREDENTIAL, credential);
        putMetadata(META_NEXT_SEQUENCE, Long.toString(nextSequence));
        putMetadata("registered", "false");
        return new Identity(installId, credential);
    }

    private int deleteExpired(long cutoffEpochMillis) {
        return database.delete("pending_events", "created_at_epoch_ms < ?",
                new String[]{Long.toString(cutoffEpochMillis)});
    }

    private int enforceBounds(int eventLimit, long byteLimit) {
        int evicted = 0;
        while (pendingCount() > eventLimit || pendingBytes() > byteLimit) {
            try (Cursor cursor = database.query("pending_events", new String[]{"row_id"}, null,
                    null, null, null, "row_id ASC", "1")) {
                if (!cursor.moveToFirst()) return evicted;
                evicted += database.delete("pending_events", "row_id = ?",
                        new String[]{Long.toString(cursor.getLong(0))});
            }
        }
        return evicted;
    }

    private QueueResult result(Identity identity, int inserted, int evicted, int expired) {
        return new QueueResult(identity.installationId, identity.credential, inserted, evicted,
                expired, pendingCount(), pendingBytes());
    }

    private int pendingCount() { return (int) android.database.DatabaseUtils.longForQuery(database, "SELECT COUNT(*) FROM pending_events", null); }
    private long pendingBytes() { return android.database.DatabaseUtils.longForQuery(database, "SELECT COALESCE(SUM(properties_bytes), 0) FROM pending_events", null); }
    private String getMetadata(String key) {
        try (Cursor cursor = database.query("metadata", new String[]{"value"}, "key = ?", new String[]{key}, null, null, null)) {
            return cursor.moveToFirst() ? cursor.getString(0) : null;
        }
    }
    private String requireMetadata(String key) { String value = getMetadata(key); if (value == null) throw new IllegalStateException("Missing metadata: " + key); return value; }
    private void putMetadata(String key, String value) { ContentValues row = new ContentValues(); row.put("key", key); row.put("value", value); database.insertWithOnConflict("metadata", null, row, SQLiteDatabase.CONFLICT_REPLACE); }
    private static boolean isUuid(String value) {
        try {
            UUID uuid = UUID.fromString(value);
            return uuid.version() == 4 && uuid.variant() == 2 && uuid.toString().equals(value);
        } catch (Exception ignored) {
            return false;
        }
    }
    private static String requireUuid(JSONObject event, String key) throws JSONException { String value = event.getString(key); if (!isUuid(value)) throw new JSONException(key + " must be a UUID."); return value; }

    private static final class Identity { final String installationId; final String credential; Identity(String installationId, String credential) { this.installationId = installationId; this.credential = credential; } }

    private static final class QueueOpenHelper extends SQLiteOpenHelper {
        QueueOpenHelper(Context context, String databasePath) { super(context, databasePath, null, DATABASE_VERSION); }
        @Override public void onConfigure(SQLiteDatabase database) {
            database.setForeignKeyConstraintsEnabled(true);
            applyPragma(database, "PRAGMA busy_timeout=2000");
            applyPragma(database, "PRAGMA synchronous=NORMAL");
            applyPragma(database, "PRAGMA wal_autocheckpoint=1000");
        }
        @Override public void onCreate(SQLiteDatabase database) {
            database.execSQL("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)");
            database.execSQL("CREATE TABLE pending_events (row_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE, install_id TEXT NOT NULL, session_id TEXT NOT NULL, sequence INTEGER NOT NULL, session_elapsed_ms INTEGER NOT NULL, name TEXT NOT NULL, occurred_at_client TEXT NOT NULL, properties_json TEXT NOT NULL, properties_bytes INTEGER NOT NULL, payload_json TEXT NOT NULL, created_at_epoch_ms INTEGER NOT NULL, attempt_count INTEGER NOT NULL DEFAULT 0)");
            database.execSQL("CREATE INDEX pending_events_created_at ON pending_events(created_at_epoch_ms)");
        }
        @Override public void onUpgrade(SQLiteDatabase database, int oldVersion, int newVersion) {
            if (oldVersion < 2)
                database.execSQL("ALTER TABLE pending_events ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0");
        }
        private static void applyPragma(SQLiteDatabase database, String statement) {
            try (Cursor ignored = database.rawQuery(statement, null)) { ignored.moveToFirst(); }
        }
    }
}
