package com.daliys.analytics;

import android.app.ActivityManager;
import android.app.ApplicationExitInfo;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import android.database.sqlite.SQLiteStatement;
import android.os.Build;
import android.util.Base64;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.Closeable;
import java.io.File;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;

/**
 * Single-owner durable queue for the Unity SDK. Callers serialize access through
 * the C# persistence worker; methods are synchronized as a defensive boundary.
 */
public final class AnalyticsQueue implements Closeable {
    static final String DATABASE_NAME = "daliys_analytics.db";
    private static final int DATABASE_VERSION = 4;
    /** Row formats: 0 = JSON payload written by SDK versions before binary records, 1 = binary event record (see EventRecord.cs). */
    static final int FORMAT_JSON = 0, FORMAT_RECORD = 1;
    private static final int RECORD_HEADER = 33;
    private static final String META_INSTALL_ID = "install_id";
    private static final String META_CREDENTIAL = "installation_credential";
    private static final String META_NEXT_SEQUENCE = "next_sequence";
    private static final String META_STREAM_BASE = "stream_base";
    private static final String META_STREAM_EPOCH = "stream_epoch";
    private static final String META_DROPPED_VERSION = "dropped_version";
    private static final String META_SESSION_STATE = "session_state";
    /** Older ranges are merged beyond this bound; a wider skip is safe because skips only mean "do not wait for". */
    private static final int MAX_DROPPED_RANGES = 1024;

    private final Context context;
    private final File databaseFile;
    private QueueOpenHelper helper;
    private SQLiteDatabase database;
    private final SecureRandom secureRandom = new SecureRandom();
    // In-memory mirrors of what the database holds, so the hot path (one transaction per flush) does no counting queries.
    // They change only under this object's lock and are rebuilt from the database whenever a transaction does not complete.
    private Identity identity;
    private long nextSequence;
    private int pendingCount;
    private long pendingBytes;
    private long lastExpiryCheckMillis;
    private SQLiteStatement insertStatement;

    public AnalyticsQueue(Context context) {
        this.context = context.getApplicationContext();
        File directory = context.getNoBackupFilesDir();
        databaseFile = new File(directory, DATABASE_NAME);
        helper = new QueueOpenHelper(this.context, databaseFile.getAbsolutePath());
        database = openDatabaseWithRecovery();
        identity = ensureIdentity();
        reloadCaches();
    }

    /** Cheap: answered from memory. */
    public synchronized QueueResult getState() {
        return new QueueResult(identity.installationId, identity.credential, 0, 0, 0, pendingCount, pendingBytes);
    }

    /**
     * Sequence state for the delivery contract: the stream starts at {@code stream_base}, issued numbers end
     * at {@code next_sequence - 1}, and {@code dropped} lists locally discarded (evicted, expired, cleared)
     * inclusive ranges that the server must not wait for. Acknowledged rows are not listed.
     */
    public synchronized String getSequenceState() throws JSONException {
        JSONArray dropped = new JSONArray();
        long[][] ranges = readDroppedRanges();
        for (long[] range : ranges) dropped.put(new JSONArray().put(range[0]).put(range[1]));
        return new JSONObject().put("install_id", identity.installationId)
                .put("stream_base", Long.parseLong(requireMetadata(META_STREAM_BASE)))
                .put("next_sequence", nextSequence)
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
            long next = nextSequence;
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
        if (deleted > 0) refreshCounters();
        return deleted;
    }

    /** Replaces only an invalid credential/identity pair; queued events and the saved session state remain. */
    public synchronized QueueResult resetIdentity() {
        database.beginTransaction();
        try {
            long next = android.database.DatabaseUtils.longForQuery(database,
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM pending_events", null);
            String sessionState = getMetadata(META_SESSION_STATE);
            database.delete("metadata", null, null);
            identity = newIdentity(next);
            if (sessionState != null) putMetadata(META_SESSION_STATE, sessionState);
            database.setTransactionSuccessful();
        } finally {
            database.endTransaction();
        }
        reloadCaches();
        return getState();
    }

    /**
     * Stores binary event records in one transaction. {@code data} is {@code count} entries of {@code int32 length (big-endian)} followed by the
     * record (format byte 1, 16-byte event id, ... see EventRecord.cs); the queue reads nothing but the id from it and assigns the sequence numbers.
     * Returns the number of rows queued afterwards.
     */
    public synchronized int enqueueRecords(byte[] data, int count, int eventLimit, long byteLimit, long maxAgeMillis) {
        if (eventLimit <= 0 || byteLimit <= 0 || maxAgeMillis <= 0)
            throw new IllegalArgumentException("Queue limits must be positive.");
        if (data == null || count < 0)
            throw new IllegalArgumentException("Invalid record batch.");

        long now = System.currentTimeMillis();
        boolean committed = false;
        database.beginTransaction();
        try {
            SQLiteStatement insert = insertStatement();
            long sequence = nextSequence;
            int position = 0;
            for (int index = 0; index < count; index++) {
                if (position + 4 > data.length) throw new IllegalArgumentException("Record batch is truncated.");
                int length = ((data[position] & 0xff) << 24) | ((data[position + 1] & 0xff) << 16) | ((data[position + 2] & 0xff) << 8) | (data[position + 3] & 0xff);
                position += 4;
                if (length < RECORD_HEADER || position + length > data.length || data[position] != FORMAT_RECORD)
                    throw new IllegalArgumentException("Record " + index + " is invalid.");
                insert.clearBindings();
                insert.bindString(1, uuidText(data, position + 1));
                insert.bindLong(2, sequence);
                insert.bindLong(3, FORMAT_RECORD);
                insert.bindBlob(4, Arrays.copyOfRange(data, position, position + length));
                insert.bindLong(5, length);
                insert.bindLong(6, now);
                if (insert.executeInsert() != -1L) {
                    sequence++;
                    pendingCount++;
                    pendingBytes += length;
                }
                position += length;
            }
            if (sequence != nextSequence) {
                putMetadata(META_NEXT_SEQUENCE, Long.toString(sequence));
                nextSequence = sequence;
            }
            expireIfDue(now, maxAgeMillis);
            enforceBounds(eventLimit, byteLimit);
            database.setTransactionSuccessful();
            committed = true;
        } finally {
            database.endTransaction();
            if (!committed) reloadCaches();
        }
        return pendingCount;
    }

    /**
     * Oldest rows first, as {@code int32 count} then per row {@code u8 format, int64 sequence, int32 length, bytes} (all big-endian).
     * Format 0 rows carry a JSON payload written by an older SDK version.
     */
    public synchronized byte[] readOldest(int maxEvents) {
        if (maxEvents <= 0) throw new IllegalArgumentException("maxEvents must be positive.");
        byte[] out = new byte[4 + Math.min(maxEvents, Math.max(1, pendingCount)) * 256];
        int length = 4;
        int rows = 0;
        try (Cursor cursor = database.query("pending_events", new String[]{"format", "sequence", "payload"}, null,
                null, null, null, "row_id ASC", Integer.toString(maxEvents))) {
            while (cursor.moveToNext()) {
                byte[] payload = cursor.getBlob(2);
                if (length + 13 + payload.length > out.length) out = Arrays.copyOf(out, Math.max(out.length * 2, length + 13 + payload.length));
                out[length++] = (byte) cursor.getInt(0);
                long sequence = cursor.getLong(1);
                for (int shift = 56; shift >= 0; shift -= 8) out[length++] = (byte) (sequence >>> shift);
                out[length++] = (byte) (payload.length >>> 24); out[length++] = (byte) (payload.length >>> 16);
                out[length++] = (byte) (payload.length >>> 8); out[length++] = (byte) payload.length;
                System.arraycopy(payload, 0, out, length, payload.length);
                length += payload.length;
                rows++;
            }
        }
        out[0] = (byte) (rows >>> 24); out[1] = (byte) (rows >>> 16); out[2] = (byte) (rows >>> 8); out[3] = (byte) rows;
        return Arrays.copyOf(out, length);
    }

    /** Saves the small session-state document the C# side keeps for session-end detection (one row, replaced). */
    public synchronized void saveSessionState(String state) {
        putMetadata(META_SESSION_STATE, state);
    }

    /** Returns the saved session state, or an empty string. */
    public synchronized String loadSessionState() {
        String state = getMetadata(META_SESSION_STATE);
        return state == null ? "" : state;
    }

    /**
     * How the previous process of this app ended (Android 11+): {@code {"reason":..,"status":..,"timestamp":..,"importance":..}} for the newest exit
     * record that is not the running process, or an empty string when the platform has none. The reason is an ApplicationExitInfo.REASON_* constant.
     */
    public synchronized String getPreviousExitInfo() {
        if (Build.VERSION.SDK_INT < 30) return "";
        try {
            ActivityManager manager = (ActivityManager) context.getSystemService(Context.ACTIVITY_SERVICE);
            List<ApplicationExitInfo> exits = manager.getHistoricalProcessExitReasons(context.getPackageName(), 0, 5);
            int own = android.os.Process.myPid();
            for (ApplicationExitInfo info : exits) {
                if (info.getPid() == own) continue;
                return new JSONObject().put("reason", info.getReason()).put("status", info.getStatus())
                        .put("timestamp", info.getTimestamp()).put("importance", info.getImportance()).put("pid", info.getPid()).toString();
            }
        } catch (Throwable ignored) {
            // best effort: no exit information
        }
        return "";
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
        if (deleted > 0) refreshCounters();
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
        pendingCount = 0;
        pendingBytes = 0;
    }

    @Override public synchronized void close() {
        if (insertStatement != null) { insertStatement.close(); insertStatement = null; }
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

    private SQLiteStatement insertStatement() {
        if (insertStatement == null)
            insertStatement = database.compileStatement("INSERT OR IGNORE INTO pending_events"
                    + "(event_id, sequence, format, payload, size, created_at_epoch_ms) VALUES (?, ?, ?, ?, ?, ?)");
        return insertStatement;
    }

    /** Rebuilds the in-memory mirrors from the database (after open, a reset, or a transaction that did not complete). */
    private void reloadCaches() {
        String next = getMetadata(META_NEXT_SEQUENCE);
        nextSequence = next == null ? 1 : Long.parseLong(next);
        refreshCounters();
    }

    private void refreshCounters() {
        pendingCount = (int) android.database.DatabaseUtils.longForQuery(database, "SELECT COUNT(*) FROM pending_events", null);
        pendingBytes = android.database.DatabaseUtils.longForQuery(database, "SELECT COALESCE(SUM(size), 0) FROM pending_events", null);
    }

    private static final char[] HEX = "0123456789abcdef".toCharArray();

    private static String uuidText(byte[] data, int offset) {
        char[] chars = new char[36];
        int out = 0;
        for (int i = 0; i < 16; i++) {
            if (i == 4 || i == 6 || i == 8 || i == 10) chars[out++] = '-';
            int b = data[offset + i] & 0xff;
            chars[out++] = HEX[b >> 4];
            chars[out++] = HEX[b & 15];
        }
        return new String(chars);
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

    /** Expiry is a housekeeping pass, not a per-write one: it runs at most every min(60 s, maxAge / 4). */
    private void expireIfDue(long now, long maxAgeMillis) {
        long interval = Math.min(60_000L, Math.max(1L, maxAgeMillis / 4));
        if (now - lastExpiryCheckMillis < interval) return;
        lastExpiryCheckMillis = now;
        String[] args = {Long.toString(now - maxAgeMillis)};
        recordDroppedWhere("created_at_epoch_ms < ?", args);
        if (database.delete("pending_events", "created_at_epoch_ms < ?", args) > 0) refreshCounters();
    }

    private void enforceBounds(int eventLimit, long byteLimit) {
        int evicted = 0;
        while (pendingCount > eventLimit || pendingBytes > byteLimit) {
            try (Cursor cursor = database.query("pending_events", new String[]{"row_id", "sequence", "size"}, null,
                    null, null, null, "row_id ASC", "1")) {
                if (!cursor.moveToFirst()) break;
                recordDropped(cursor.getLong(1));
                evicted += database.delete("pending_events", "row_id = ?", new String[]{Long.toString(cursor.getLong(0))});
                pendingCount--;
                pendingBytes -= cursor.getLong(2);
            }
        }
        if (evicted > 0) bumpDroppedVersion();
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
            long firstTo = cursor.getLong(1);
            cursor.moveToNext();
            long secondFrom = cursor.getLong(0);
            long secondTo = cursor.getLong(1);
            // The widened range declares the gap settled, so rows still queued in it must go with it (an honest,
            // journaled drop) instead of being silently removed by the next ack.
            database.delete("pending_events", "sequence > ? AND sequence < ?",
                    new String[]{Long.toString(firstTo), Long.toString(secondFrom)});
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
            createPendingTable(database, "pending_events");
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
            if (oldVersion < 4) {
                // Rows become (format, payload, size). Queued JSON payloads are kept as format 0 and converted by the C# reader when sent.
                createPendingTable(database, "pending_events_v4");
                database.execSQL("INSERT INTO pending_events_v4 (row_id, event_id, sequence, format, payload, size, created_at_epoch_ms, attempt_count) "
                        + "SELECT row_id, event_id, sequence, 0, CAST(payload_json AS BLOB), LENGTH(CAST(payload_json AS BLOB)), created_at_epoch_ms, attempt_count FROM pending_events");
                database.execSQL("DROP TABLE pending_events");
                database.execSQL("ALTER TABLE pending_events_v4 RENAME TO pending_events");
                database.execSQL("CREATE INDEX pending_events_created_at ON pending_events(created_at_epoch_ms)");
                database.execSQL("CREATE INDEX pending_events_sequence ON pending_events(sequence)");
            }
        }
        private static void createPendingTable(SQLiteDatabase database, String name) {
            database.execSQL("CREATE TABLE " + name + " (row_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE, sequence INTEGER NOT NULL, format INTEGER NOT NULL, payload BLOB NOT NULL, size INTEGER NOT NULL, created_at_epoch_ms INTEGER NOT NULL, attempt_count INTEGER NOT NULL DEFAULT 0)");
            if (name.equals("pending_events")) {
                database.execSQL("CREATE INDEX pending_events_created_at ON pending_events(created_at_epoch_ms)");
                database.execSQL("CREATE INDEX pending_events_sequence ON pending_events(sequence)");
            }
        }
        private static void applyPragma(SQLiteDatabase database, String statement) {
            try (Cursor ignored = database.rawQuery(statement, null)) { ignored.moveToFirst(); }
        }
    }
}
