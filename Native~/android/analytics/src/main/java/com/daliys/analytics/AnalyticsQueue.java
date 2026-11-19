// Durable SQLite event queue of the Android SDK: records, sequence stream, dropped-range journal and identity.
package com.daliys.analytics;

import static com.daliys.analytics.QueueProfiler.*;

import android.app.ActivityManager;
import android.app.ApplicationExitInfo;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
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
    /** Row formats: 0 = JSON payload written by SDK versions before binary records, 1 = binary event record (see EventRecord.cs). */
    static final int FORMAT_JSON = 0, FORMAT_RECORD = 1;
    private static final int RECORD_HEADER = 33;
    private static final String META_INSTALL_ID = "install_id";
    private static final String META_CREDENTIAL = "installation_credential";
    private static final String META_NEXT_SEQUENCE = "next_sequence";
    private static final String META_STREAM_BASE = "stream_base";
    private static final String META_STREAM_EPOCH = "stream_epoch";
    private static final String META_SESSION_STATE = "session_state";
    private static final String META_COUNTERS = "counters";
    private static final String META_EVICTED_TOTAL = "evicted_total";
    /** What a stored event costs besides its payload (SQLite row, indexes): counted against the byte limit so it bounds the disk the queue really uses. */
    private static final long ROW_OVERHEAD = 40;

    private final Context context;
    private QueueOpenHelper helper;
    private SQLiteDatabase database;
    private QueueJournal journal;
    private final SecureRandom secureRandom = new SecureRandom();
    // In-memory mirrors of what the database holds, so the hot path (one transaction per flush) does no counting queries.
    // They change only under this object's lock and are rebuilt from the database whenever a transaction does not complete.
    private Identity identity;
    private long nextSequence;
    private int pendingCount;
    private long pendingBytes;
    private long lastExpiryCheckMillis;
    private SQLiteStatement insertStatement;
    private final QueueProfiler prof = new QueueProfiler();
    // Bounds of every enqueue, set once by setLimits (eventLimit -1 = not set yet).
    private int eventLimit = -1;
    private long byteLimit;
    private long maxAgeMillis;

    public AnalyticsQueue(Context context) {
        this.context = context.getApplicationContext();
        helper = QueueOpenHelper.openWithRecovery(this.context, new File(context.getNoBackupFilesDir(), DATABASE_NAME));
        database = helper.openWritable();
        journal = new QueueJournal(database);
        identity = ensureIdentity();
        reloadCaches();
    }

    /** Cheap: answered from memory. */
    public synchronized QueueResult getState() {
        long p0 = prof.begin();
        QueueResult result = new QueueResult(identity.installationId, identity.credential, 0, 0, 0, pendingCount, pendingBytes);
        prof.end(P_STATE, p0);
        return result;
    }

    /**
     * Sequence state for the delivery contract: the stream starts at {@code stream_base}, issued numbers end
     * at {@code next_sequence - 1}, and {@code dropped} lists locally discarded (evicted, expired, cleared)
     * inclusive ranges that the server must not wait for. Acknowledged rows are not listed.
     */
    public synchronized String getSequenceState() throws JSONException {
        long p0 = prof.begin();
        try {
            return sequenceStateText();
        } finally {
            prof.end(P_SEQ_STATE, p0);
        }
    }

    private String sequenceStateText() throws JSONException {
        JSONArray dropped = new JSONArray();
        long[][] ranges = journal.ranges();
        for (long[] range : ranges) dropped.put(new JSONArray().put(range[0]).put(range[1]));
        return new JSONObject().put("install_id", identity.installationId)
                .put("stream_base", Long.parseLong(journal.require(META_STREAM_BASE)))
                .put("next_sequence", nextSequence)
                .put("stream_epoch", journal.getLong(META_STREAM_EPOCH, 0))
                .put("dropped_version", journal.getLong(QueueJournal.DROPPED_VERSION, 0))
                .put("dropped", dropped).toString();
    }

    /** Records the epoch the server issued for this installation's V7 stream (0 clears it). */
    public synchronized void setStreamEpoch(long epoch) {
        if (epoch < 0) throw new IllegalArgumentException("epoch must not be negative");
        journal.put(META_STREAM_EPOCH, Long.toString(epoch));
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
            journal.put(META_STREAM_BASE, Long.toString(base));
            journal.put(META_STREAM_EPOCH, "0");
            // Gaps between queued rows stay: those rows keep their numbers, and the server must be told the gaps are closed.
            database.delete("dropped_ranges", "to_sequence < ?", new String[]{Long.toString(base)});
            journal.bumpVersion();
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
        long p0 = prof.begin();
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
        prof.end(P_DELETE, p0);
        return deleted;
    }

    /** Replaces only an invalid credential/identity pair; queued events and the saved session state remain. */
    public synchronized QueueResult resetIdentity() {
        database.beginTransaction();
        try {
            long next = android.database.DatabaseUtils.longForQuery(database,
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM pending_events", null);
            java.util.List<String[]> kept = readKeptMetadata();
            database.delete("metadata", null, null);
            identity = newIdentity(next);
            for (String[] pair : kept) journal.put(pair[0], pair[1]);
            database.setTransactionSuccessful();
        } finally {
            try {
                database.endTransaction();
            } catch (RuntimeException failure) {
                identity = ensureIdentity(); // the commit failed: take the identity back from the database
                throw failure;
            }
        }
        reloadCaches();
        return getState();
    }

    private static boolean isAppMetaKey(String key) {
        return key.equals(META_SESSION_STATE) || key.equals(META_COUNTERS) || key.equals(META_EVICTED_TOTAL) || (key.startsWith("v8.") && key.length() <= 32);
    }

    /** The rows an identity reset must not touch: the saved session state, the counters and what the V8 transport keeps here. */
    private java.util.List<String[]> readKeptMetadata() {
        java.util.List<String[]> kept = new java.util.ArrayList<>();
        try (Cursor cursor = database.query("metadata", new String[]{"key", "value"}, null, null, null, null, null)) {
            while (cursor.moveToNext()) if (isAppMetaKey(cursor.getString(0))) kept.add(new String[]{cursor.getString(0), cursor.getString(1)});
        }
        return kept;
    }

    /** Reads a value the SDK keeps in the queue's durable storage ("v8.*" keys and "counters"); a missing key reads as the empty string. */
    public synchronized String getMeta(String key) {
        if (key == null || !isAppMetaKey(key)) throw new IllegalArgumentException("Not a storage key: " + key);
        long p0 = prof.begin();
        String value = journal.get(key);
        prof.end(P_META_GET, p0);
        return value == null ? "" : value;
    }

    public synchronized void setMeta(String key, String value) {
        if (key == null || !isAppMetaKey(key)) throw new IllegalArgumentException("Not a storage key: " + key);
        if (value == null || value.length() > 262144) throw new IllegalArgumentException("Invalid storage value.");
        long p0 = prof.begin();
        journal.put(key, value);
        prof.end(P_META_SET, p0);
    }

    /**
     * Takes the installation identity the V8 server issued (internal id and credential), so a batch the V8 transport has to send through V1 belongs to the
     * same installation and carries the ids the server derives. Queued rows, sequence numbers and the stream are untouched.
     */
    public synchronized void adoptIdentity(String installationId, String credential) {
        if (!isUuid(installationId) || credential == null || credential.length() != 43)
            throw new IllegalArgumentException("Invalid installation identity.");
        if (installationId.equals(identity.installationId) && credential.equals(identity.credential)) return;
        database.beginTransaction();
        try {
            journal.put(META_INSTALL_ID, installationId);
            journal.put(META_CREDENTIAL, credential);
            database.setTransactionSuccessful();
        } finally {
            database.endTransaction();
        }
        identity = new Identity(installationId, credential);
    }

    public synchronized void setProfiling(boolean on) { prof.setEnabled(on); }

    /** Per stage: calls, wall ns, thread CPU ns (totals only), ART bytes allocated across the stage (totals only; all threads), longest call ns. */
    public synchronized String getProfile() throws JSONException { return prof.json(); }

    /**
     * Bounds every later enqueue applies: at most {@code eventLimit} rows (0 = no limit by count), {@code byteLimit} bytes including row overhead
     * (must be positive), rows older than {@code maxAgeMillis} expire (0 = no expiry). Must be called before the first enqueue.
     */
    public synchronized void setLimits(int eventLimit, long byteLimit, long maxAgeMillis) {
        if (eventLimit < 0 || byteLimit <= 0 || maxAgeMillis < 0)
            throw new IllegalArgumentException("Queue limits must not be negative and the byte limit must be positive (0 = no limit by count / no expiry).");
        this.eventLimit = eventLimit == 0 ? Integer.MAX_VALUE : eventLimit;
        this.byteLimit = byteLimit;
        this.maxAgeMillis = maxAgeMillis;
    }

    /**
     * Stores binary event records in one transaction. {@code data} is {@code count} entries of {@code int32 length (big-endian)} followed by the
     * record (format byte 1, 16-byte event id, ... see EventRecord.cs); the queue reads nothing but the id from it and assigns the sequence numbers.
     * Returns the number of rows queued afterwards.
     */

    public synchronized int enqueueRecords(byte[] data, int count) {
        return enqueueRecords(data, count, null);
    }

    /**
     * As above, and stores {@code counters} (the SDK's counter values, JSON) in the same transaction when it is neither null nor empty: after a crash a counter and the
     * events that used its numbers are either both there or both gone.
     */
    public synchronized int enqueueRecords(byte[] data, int count, String counters) {
        if (eventLimit < 0) throw new IllegalStateException("setLimits must be called before the first enqueue.");
        if (counters != null && counters.length() > 65536)
            throw new IllegalArgumentException("Invalid counters.");
        if (data == null || count < 0)
            throw new IllegalArgumentException("Invalid record batch.");

        long now = System.currentTimeMillis();
        boolean committed = false;
        long pTotal = prof.begin(), pCpu = prof.cpuBegin(), pAlloc = prof.allocBegin();
        database.beginTransaction();
        try {
            long pLoop = prof.begin();
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
                long pExec = prof.begin();
                if (insert.executeInsert() != -1L) {
                    sequence++;
                    pendingCount++;
                    pendingBytes += length;
                }
                prof.end(P_INSERT_EXEC, pExec);
                position += length;
            }
            prof.end(P_INSERT_LOOP, pLoop);
            long pStage = prof.begin();
            if (sequence != nextSequence) {
                journal.put(META_NEXT_SEQUENCE, Long.toString(sequence));
                nextSequence = sequence;
            }
            prof.end(P_META_SEQ, pStage);
            pStage = prof.begin();
            if (maxAgeMillis > 0) expireIfDue(now, maxAgeMillis);
            prof.end(P_EXPIRE, pStage);
            pStage = prof.begin();
            enforceBounds(eventLimit, byteLimit);
            prof.end(P_BOUNDS, pStage);
            pStage = prof.begin();
            if (counters != null && !counters.isEmpty()) journal.put(META_COUNTERS, counters);
            prof.end(P_COUNTERS, pStage);
            database.setTransactionSuccessful();
            committed = true;
        } finally {
            boolean ended = false;
            long pCommit = prof.begin();
            try {
                database.endTransaction();
                ended = true;
            } finally {
                prof.end(P_COMMIT, pCommit);
                if (!committed || !ended) reloadCaches(); // a failed commit leaves the cached counters ahead of the database
            }
        }
        prof.endTotal(P_ENQ, pTotal, pCpu, pAlloc);
        return pendingCount;
    }

    /**
     * Oldest rows first, as {@code int32 count} then per row {@code u8 format, int64 sequence, int32 length, bytes} (all big-endian).
     * Format 0 rows carry a JSON payload written by an older SDK version.
     */
    public synchronized byte[] readOldest(int maxEvents) {
        if (maxEvents <= 0) throw new IllegalArgumentException("maxEvents must be positive.");
        long pTotal = prof.begin(), pCpu = prof.cpuBegin(), pAlloc = prof.allocBegin();
        byte[] out = new byte[4 + Math.min(maxEvents, Math.max(1, pendingCount)) * 256];
        int length = 4;
        int rows = 0;
        long pQuery = prof.begin();
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
        prof.end(P_READ_QUERY, pQuery);
        out[0] = (byte) (rows >>> 24); out[1] = (byte) (rows >>> 16); out[2] = (byte) (rows >>> 8); out[3] = (byte) rows;
        byte[] result = Arrays.copyOf(out, length);
        prof.endTotal(P_READ, pTotal, pCpu, pAlloc);
        return result;
    }

    /** Saves the small session-state document the C# side keeps for session-end detection (one row, replaced). */
    public synchronized void saveSessionState(String state) {
        long p0 = prof.begin();
        journal.put(META_SESSION_STATE, state);
        prof.end(P_SESSION_SAVE, p0);
    }

    /** Returns the saved session state, or an empty string. */
    public synchronized String loadSessionState() {
        long p0 = prof.begin();
        String state = journal.get(META_SESSION_STATE);
        prof.end(P_SESSION_LOAD, p0);
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
            boolean streamOpen = journal.getLong(META_STREAM_EPOCH, 0) > 0;
            for (int index = 0; index < ids.length(); index++) {
                String[] id = new String[]{ids.getString(index)};
                if (streamOpen) journal.recordWhere("event_id = ?", id);
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
            journal.recordWhere(null, null);
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

    private SQLiteStatement insertStatement() {
        if (insertStatement == null)
            insertStatement = database.compileStatement("INSERT OR IGNORE INTO pending_events"
                    + "(event_id, sequence, format, payload, size, created_at_epoch_ms) VALUES (?, ?, ?, ?, ?, ?)");
        return insertStatement;
    }

    /** Rebuilds the in-memory mirrors from the database (after open, a reset, or a transaction that did not complete). */
    private void reloadCaches() {
        String next = journal.get(META_NEXT_SEQUENCE);
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
            String installId = journal.get(META_INSTALL_ID);
            String credential = journal.get(META_CREDENTIAL);
            if (!isUuid(installId) || credential == null || credential.isEmpty()) {
                database.delete("pending_events", null, null);
                java.util.List<String[]> kept = readKeptMetadata();
                database.delete("metadata", null, null);
                Identity identity = newIdentity(1);
                for (String[] pair : kept) journal.put(pair[0], pair[1]);
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
        journal.put(META_INSTALL_ID, installId);
        journal.put(META_CREDENTIAL, credential);
        journal.put(META_NEXT_SEQUENCE, Long.toString(nextSequence));
        // The new stream starts at the lowest queued row (rows keep their numbers) or at the next number.
        long streamBase = android.database.DatabaseUtils.longForQuery(database,
                "SELECT COALESCE(MIN(sequence), ?) FROM pending_events", new String[]{Long.toString(nextSequence)});
        journal.put(META_STREAM_BASE, Long.toString(streamBase));
        database.delete("dropped_ranges", "to_sequence < ?", new String[]{Long.toString(streamBase)});
        journal.put("registered", "false");
        return new Identity(installId, credential);
    }

    /** Expiry is a housekeeping pass, not a per-write one: it runs at most every min(60 s, maxAge / 4). */
    private void expireIfDue(long now, long maxAgeMillis) {
        long interval = Math.min(60_000L, Math.max(1L, maxAgeMillis / 4));
        if (now - lastExpiryCheckMillis < interval) return;
        lastExpiryCheckMillis = now;
        String[] args = {Long.toString(now - maxAgeMillis)};
        journal.recordWhere("created_at_epoch_ms < ?", args);
        int expired = database.delete("pending_events", "created_at_epoch_ms < ?", args);
        if (expired > 0) {
            refreshCounters();
            journal.put(META_EVICTED_TOTAL, Long.toString(journal.getLong(META_EVICTED_TOTAL, 0) + expired));
        }
    }

    private void enforceBounds(int eventLimit, long byteLimit) {
        int evicted = 0;
        while (pendingCount > eventLimit || pendingBytes + ROW_OVERHEAD * pendingCount > byteLimit) {
            try (Cursor cursor = database.query("pending_events", new String[]{"row_id", "sequence", "size"}, null,
                    null, null, null, "row_id ASC", "1")) {
                if (!cursor.moveToFirst()) break;
                journal.record(cursor.getLong(1));
                evicted += database.delete("pending_events", "row_id = ?", new String[]{Long.toString(cursor.getLong(0))});
                pendingCount--;
                pendingBytes -= cursor.getLong(2);
            }
        }
        if (evicted > 0) {
            journal.bumpVersion();
            journal.put(META_EVICTED_TOTAL, Long.toString(journal.getLong(META_EVICTED_TOTAL, 0) + evicted));
        }
    }

    private static boolean isUuid(String value) {
        try {
            UUID uuid = UUID.fromString(value);
            return uuid.version() == 4 && uuid.variant() == 2 && uuid.toString().equals(value);
        } catch (Exception ignored) {
            return false;
        }
    }

    private static final class Identity { final String installationId; final String credential; Identity(String installationId, String credential) { this.installationId = installationId; this.credential = credential; } }

}
