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
    private static final int DATABASE_VERSION = 3;
    private static final String META_INSTALL_ID = "install_id";
    private static final String META_CREDENTIAL = "installation_credential";
    private static final String META_NEXT_SEQUENCE = "next_sequence";
    private static final String META_STREAM_BASE = "stream_base";
    private static final String META_STREAM_EPOCH = "stream_epoch";
    private static final String META_DROPPED_VERSION = "dropped_version";
    /** Older ranges are merged beyond this bound; a wider skip is safe because skips only mean "do not wait for". */
    private static final int MAX_DROPPED_RANGES = 1024;

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

    /**
     * Sequence state for the delivery contract: the stream starts at {@code stream_base}, issued numbers end
     * at {@code next_sequence - 1}, and {@code dropped} lists locally discarded (evicted, expired, cleared)
     * inclusive ranges that the server must not wait for. Acknowledged rows are not listed.
     */
    public synchronized String getSequenceState() throws JSONException {
        Identity identity = ensureIdentity();
        JSONArray dropped = new JSONArray();
        long[][] ranges = readDroppedRanges();
        for (long[] range : ranges) dropped.put(new JSONArray().put(range[0]).put(range[1]));
        return new JSONObject().put("install_id", identity.installationId)
                .put("stream_base", Long.parseLong(requireMetadata(META_STREAM_BASE)))
                .put("next_sequence", Long.parseLong(requireMetadata(META_NEXT_SEQUENCE)))
                .put("stream_epoch", longMetadata(META_STREAM_EPOCH, 0))
                .put("dropped_version", longMetadata(META_DROPPED_VERSION, 0))
                .put("dropped", dropped).toString();
    }

    /** Records the epoch the server issued for this installation's V7 stream (0 clears it). */
    public synchronized void setStreamEpoch(long epoch) {
        if (epoch < 0) throw new IllegalArgumentException("epoch must not be negative");
        putMetadata(META_STREAM_EPOCH, Long.toString(epoch));
    }

    /**
     * Starts a new stream for the rows still queued (after the server refused the old one, e.g. a rolled-back counter):
     * the stream begins at the lowest queued sequence, ranges below it are forgotten and the epoch is cleared so the next
     * sync opens a fresh one. Queued rows keep their numbers.
     */
    public synchronized void beginNewStream() {
        database.beginTransaction();
        try {
            long next = Long.parseLong(requireMetadata(META_NEXT_SEQUENCE));
            long base = android.database.DatabaseUtils.longForQuery(database,
                    "SELECT COALESCE(MIN(sequence), ?) FROM pending_events", new String[]{Long.toString(next)});
            putMetadata(META_STREAM_BASE, Long.toString(base));
            putMetadata(META_STREAM_EPOCH, "0");
            database.delete("dropped_ranges", null, null);
            bumpDroppedVersion();
            database.setTransactionSuccessful();
        } finally {
            database.endTransaction();
        }
    }

    /**
     * Deletes every queued row with sequence <= ackThrough: the server confirmed that range as received, rejected or
     * announced dropped. The rows are NOT journaled as dropped (they were delivered). Journal ranges the server has now
     * settled are pruned. Returns the number of deleted rows.
     */
    public synchronized int deleteThroughSequence(long ackThrough) {
        int deleted;
        database.beginTransaction();
        try {
            deleted = database.delete("pending_events", "sequence <= ?", new String[]{Long.toString(ackThrough)});
            database.delete("dropped_ranges", "to_sequence <= ?", new String[]{Long.toString(ackThrough)});
            // A range straddling the ack keeps only its unsettled tail (from_sequence is the key: rewrite it).
            try (Cursor cursor = database.query("dropped_ranges", new String[]{"from_sequence", "to_sequence"}, "from_sequence <= ?",
                    new String[]{Long.toString(ackThrough)}, null, null, null)) {
                while (cursor.moveToNext()) {
                    long to = cursor.getLong(1);
                    database.delete("dropped_ranges", "from_sequence = ?", new String[]{Long.toString(cursor.getLong(0))});
                    ContentValues tail = new ContentValues();
                    tail.put("from_sequence", ackThrough + 1);
                    tail.put("to_sequence", to);
                    database.insertWithOnConflict("dropped_ranges", null, tail, SQLiteDatabase.CONFLICT_REPLACE);
                }
            }
            database.setTransactionSuccessful();
        } finally {
            database.endTransaction();
        }
        return deleted;
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
            // Rows delivered through V1 bypass the V7 stream: once a stream is open, tell the server not to wait for them.
            boolean streamOpen = longMetadata(META_STREAM_EPOCH, 0) > 0;
            for (int index = 0; index < ids.length(); index++) {
                String[] id = new String[]{ids.getString(index)};
                if (streamOpen) recordDroppedWhere("event_id = ?", id);
                deleted += database.delete("pending_events", "event_id = ?", id);
            }
            database.setTransactionSuccessful();
        } finally {
            database.endTransaction();
        }
        return deleted;
    }

    /** Removes every durable event when collection is revoked with clear-pending enabled. */
    public synchronized void clearAllPendingEvents() {
        database.beginTransaction();
        try {
            recordDroppedWhere(null, null);
            database.delete("pending_events", null, null);
            database.setTransactionSuccessful();
        } finally {
            database.endTransaction();
        }
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
        // The new stream starts at the lowest queued row (rows keep their numbers) or at the next number.
        long streamBase = android.database.DatabaseUtils.longForQuery(database,
                "SELECT COALESCE(MIN(sequence), ?) FROM pending_events", new String[]{Long.toString(nextSequence)});
        putMetadata(META_STREAM_BASE, Long.toString(streamBase));
        database.delete("dropped_ranges", null, null);
        putMetadata("registered", "false");
        return new Identity(installId, credential);
    }

    private int deleteExpired(long cutoffEpochMillis) {
        String[] args = {Long.toString(cutoffEpochMillis)};
        recordDroppedWhere("created_at_epoch_ms < ?", args);
        return database.delete("pending_events", "created_at_epoch_ms < ?", args);
    }

    private int enforceBounds(int eventLimit, long byteLimit) {
        int evicted = 0;
        while (pendingCount() > eventLimit || pendingBytes() > byteLimit) {
            try (Cursor cursor = database.query("pending_events", new String[]{"row_id", "sequence"}, null,
                    null, null, null, "row_id ASC", "1")) {
                if (!cursor.moveToFirst()) break;
                recordDropped(cursor.getLong(1));
                evicted += database.delete("pending_events", "row_id = ?",
                        new String[]{Long.toString(cursor.getLong(0))});
            }
        }
        if (evicted > 0) bumpDroppedVersion();
        return evicted;
    }

    private QueueResult result(Identity identity, int inserted, int evicted, int expired) {
        return new QueueResult(identity.installationId, identity.credential, inserted, evicted,
                expired, pendingCount(), pendingBytes());
    }

    /** Journals the sequences of rows about to be deleted without acknowledgement. */
    private void recordDroppedWhere(String where, String[] args) {
        try (Cursor cursor = database.query("pending_events", new String[]{"sequence"}, where, args,
                null, null, "sequence ASC")) {
            boolean any = false;
            while (cursor.moveToNext()) { recordDropped(cursor.getLong(0)); any = true; }
            if (any) bumpDroppedVersion();
        }
    }

    private void bumpDroppedVersion() {
        putMetadata(META_DROPPED_VERSION, Long.toString(longMetadata(META_DROPPED_VERSION, 0) + 1));
    }

    private long longMetadata(String key, long fallback) {
        String value = getMetadata(key);
        return value == null ? fallback : Long.parseLong(value);
    }

    private void recordDropped(long sequence) {
        ContentValues extend = new ContentValues();
        extend.put("to_sequence", sequence);
        if (database.update("dropped_ranges", extend, "to_sequence = ?", new String[]{Long.toString(sequence - 1)}) > 0)
            return;
        ContentValues range = new ContentValues();
        range.put("from_sequence", sequence);
        range.put("to_sequence", sequence);
        database.insertWithOnConflict("dropped_ranges", null, range, SQLiteDatabase.CONFLICT_IGNORE);
        if (android.database.DatabaseUtils.queryNumEntries(database, "dropped_ranges") > MAX_DROPPED_RANGES)
            mergeOldestDroppedRanges();
    }

    private void mergeOldestDroppedRanges() {
        try (Cursor cursor = database.query("dropped_ranges", new String[]{"from_sequence", "to_sequence"}, null,
                null, null, null, "from_sequence ASC", "2")) {
            if (cursor.getCount() < 2) return;
            cursor.moveToFirst();
            long firstFrom = cursor.getLong(0);
            cursor.moveToNext();
            long secondFrom = cursor.getLong(0);
            long secondTo = cursor.getLong(1);
            ContentValues widened = new ContentValues();
            widened.put("to_sequence", secondTo);
            database.update("dropped_ranges", widened, "from_sequence = ?", new String[]{Long.toString(firstFrom)});
            database.delete("dropped_ranges", "from_sequence = ?", new String[]{Long.toString(secondFrom)});
        }
    }

    private long[][] readDroppedRanges() {
        try (Cursor cursor = database.query("dropped_ranges", new String[]{"from_sequence", "to_sequence"}, null,
                null, null, null, "from_sequence ASC")) {
            long[][] ranges = new long[cursor.getCount()][];
            int index = 0;
            while (cursor.moveToNext()) ranges[index++] = new long[]{cursor.getLong(0), cursor.getLong(1)};
            return ranges;
        }
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
            database.execSQL("CREATE TABLE dropped_ranges (from_sequence INTEGER PRIMARY KEY, to_sequence INTEGER NOT NULL)");
        }
        @Override public void onUpgrade(SQLiteDatabase database, int oldVersion, int newVersion) {
            if (oldVersion < 2)
                database.execSQL("ALTER TABLE pending_events ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0");
            if (oldVersion < 3) {
                database.execSQL("CREATE TABLE dropped_ranges (from_sequence INTEGER PRIMARY KEY, to_sequence INTEGER NOT NULL)");
                // Queues written before the journal have no drop history: the stream starts at the oldest queued row.
                database.execSQL("INSERT OR IGNORE INTO metadata(key, value) SELECT 'stream_base', CAST(COALESCE("
                        + "(SELECT MIN(sequence) FROM pending_events), (SELECT value FROM metadata WHERE key = 'next_sequence'), 1) AS TEXT) "
                        + "WHERE EXISTS (SELECT 1 FROM metadata WHERE key = 'install_id')");
            }
        }
        private static void applyPragma(SQLiteDatabase database, String statement) {
            try (Cursor ignored = database.rawQuery(statement, null)) { ignored.moveToFirst(); }
        }
    }
}
