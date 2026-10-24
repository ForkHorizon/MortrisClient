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
            testLocallyDroppedSequencesAreJournaledButAcknowledgedOnesAreNot(getTargetContext());
            testResetIdentityStartsANewStreamAtTheLowestQueuedSequence(getTargetContext());
            testDeleteThroughSequenceSettlesRowsWithoutJournalingAndPrunesTheJournal(getTargetContext());
            testV1AcknowledgementIsJournaledOnlyWhileAStreamIsOpen(getTargetContext());
            testBeginNewStreamForgetsTheOldEpochAndRangesBelowTheLowestRow(getTargetContext());
            testSequenceStateReportsEpochAndDroppedVersion(getTargetContext());
            testCompactingTheDroppedJournalNeverCoversALiveRow(getTargetContext());
            testCountersFollowTheRowsAcrossAcksDeletesAndReopen(getTargetContext());
            testDuplicateEventIdDoesNotConsumeASequence(getTargetContext());
            testInvalidRecordsRollBackTheWholeBatch(getTargetContext());
            testSessionStateAndExitInfo(getTargetContext());
            testLargeBatchesKeepOrderAndPayloadBytes(getTargetContext());
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
        enqueue(queue, EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS, eventId);
        QueueResult beforeClose = queue.getState();
        String installationId = beforeClose.getInstallationId();
        String credential = beforeClose.getInstallationCredential();
        queue.close();
        queue = new AnalyticsQueue(context);

        QueueResult reopened = queue.getState();
        JSONArray pending = new JSONArray(pendingJson(queue, EVENT_LIMIT));

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

        enqueue(queue, 2, BYTE_LIMIT, MAX_AGE_MILLIS, oldestId, middleId, newestId);
        JSONArray pending = new JSONArray(pendingJson(queue, EVENT_LIMIT));

        assertEquals(2, queue.getState().getPendingCount());
        assertEquals(1, new JSONObject(queue.getSequenceState()).getJSONArray("dropped").length()); // the evicted row is journaled
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
        enqueue(queue, EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS, "44444444-4444-4444-8444-444444444444");
        QueueResult beforeCorruption = queue.getState();
        File databaseFile = databaseFile(context);
        queue.close();
        deleteDatabaseFiles(databaseFile);
        try (FileOutputStream corrupt = new FileOutputStream(databaseFile)) {
            corrupt.write(new byte[] {0x42, 0x41, 0x44, 0x21});
        }

        queue = new AnalyticsQueue(context);
        QueueResult recovered = queue.getState();

        assertNotEquals(beforeCorruption.getInstallationId(), recovered.getInstallationId());
        assertEquals(0, new JSONArray(pendingJson(queue, EVENT_LIMIT)).length());
        queue.close();
    }

    private static void testVersionOneDatabaseUpgradesWithoutDroppingQueuedEvent(Context context) throws Exception {
        File databaseFile = databaseFile(context);
        deleteDatabaseFiles(databaseFile);
        createVersionOneDatabase(databaseFile);

        AnalyticsQueue queue = new AnalyticsQueue(context);
        JSONArray pending = new JSONArray(pendingJson(queue, EVENT_LIMIT));

        assertEquals(1, pending.length());
        assertEquals("55555555-5555-4555-8555-555555555555", pending.getJSONObject(0).getString("event_id"));
        assertEquals(false, pending.getJSONObject(0).has("install_id"));
        assertEquals(true, hasAttemptCountColumn(databaseFile));
        JSONObject state = new JSONObject(queue.getSequenceState());
        assertEquals(7L, state.getLong("stream_base"));
        assertEquals(8L, state.getLong("next_sequence"));
        assertEquals("[]", state.getJSONArray("dropped").toString());
        queue.close();
    }

    private static void testResetIdentityKeepsQueuedEventsAndAdvancesSequence(Context context) throws Exception {
        AnalyticsQueue queue = new AnalyticsQueue(context);
        queue.clearAllPendingEvents();
        enqueue(queue, EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS, "66666666-6666-4666-8666-666666666666");
        QueueResult beforeReset = queue.getState();
        long firstSequence = new JSONArray(pendingJson(queue, EVENT_LIMIT)).getJSONObject(0).getLong("sequence");

        QueueResult afterReset = queue.resetIdentity();
        enqueue(queue, EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS, "77777777-7777-4777-8777-777777777777");
        JSONArray pending = new JSONArray(pendingJson(queue, EVENT_LIMIT));

        assertNotEquals(beforeReset.getInstallationId(), afterReset.getInstallationId());
        assertEquals(2, pending.length());
        assertEquals(firstSequence + 1L, pending.getJSONObject(1).getLong("sequence"));
        queue.close();
    }

    private static void testLocallyDroppedSequencesAreJournaledButAcknowledgedOnesAreNot(Context context) throws Exception {
        AnalyticsQueue queue = freshQueue(context);
        // Eviction: five events, room for two -> sequences 1..3 are dropped as one range.
        enqueue(queue, 2, BYTE_LIMIT, MAX_AGE_MILLIS, id(1), id(2), id(3), id(4), id(5));
        JSONObject state = new JSONObject(queue.getSequenceState());
        assertEquals(1L, state.getLong("stream_base"));
        assertEquals(6L, state.getLong("next_sequence"));
        assertEquals("[[1,3]]", state.getJSONArray("dropped").toString());

        // Acknowledged rows are delivered, never journaled as dropped.
        queue.deleteAcknowledged(new JSONArray().put(id(4)).toString());
        assertEquals("[[1,3]]", new JSONObject(queue.getSequenceState()).getJSONArray("dropped").toString());

        // Clearing pending data (consent revoked) journals what was still queued and merges adjacent ranges.
        queue.clearAllPendingEvents();
        state = new JSONObject(queue.getSequenceState());
        assertEquals("[[1,3],[5,5]]", state.getJSONArray("dropped").toString());
        assertEquals(6L, state.getLong("next_sequence"));
        queue.close();

        // Expiry: the older row is deleted by age while the newest survives.
        queue = freshQueue(context);
        enqueue(queue, EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS, id(6));
        Thread.sleep(40);
        enqueue(queue, EVENT_LIMIT, BYTE_LIMIT, 20L, id(7));
        assertEquals("[[1,1]]", new JSONObject(queue.getSequenceState()).getJSONArray("dropped").toString());
        queue.close();
    }

    private static void testResetIdentityStartsANewStreamAtTheLowestQueuedSequence(Context context) throws Exception {
        AnalyticsQueue queue = freshQueue(context);
        enqueue(queue, 2, BYTE_LIMIT, MAX_AGE_MILLIS, id(8), id(9), id(10)); // sequence 1 evicted
        QueueResult before = queue.getState();
        assertEquals("[[1,1]]", new JSONObject(queue.getSequenceState()).getJSONArray("dropped").toString());

        QueueResult after = queue.resetIdentity();
        JSONObject state = new JSONObject(queue.getSequenceState());

        assertNotEquals(before.getInstallationId(), after.getInstallationId());
        assertEquals(2L, state.getLong("stream_base"));
        assertEquals(4L, state.getLong("next_sequence"));
        assertEquals("[]", state.getJSONArray("dropped").toString());
        assertEquals(2, new JSONArray(pendingJson(queue, EVENT_LIMIT)).length());
        queue.close();
    }

    private static void testDeleteThroughSequenceSettlesRowsWithoutJournalingAndPrunesTheJournal(Context context) throws Exception {
        AnalyticsQueue queue = freshQueue(context);
        enqueue(queue, 4, BYTE_LIMIT, MAX_AGE_MILLIS, id(20), id(21), id(22), id(23), id(24), id(25)); // 1,2 evicted
        assertEquals("[[1,2]]", new JSONObject(queue.getSequenceState()).getJSONArray("dropped").toString());

        int deleted = queue.deleteThroughSequence(4); // rows 3 and 4 are settled by the server
        JSONObject state = new JSONObject(queue.getSequenceState());
        JSONArray pending = new JSONArray(pendingJson(queue, EVENT_LIMIT));

        assertEquals(2, deleted);
        assertEquals(2, pending.length());
        assertEquals(5L, pending.getJSONObject(0).getLong("sequence"));
        assertEquals("[]", state.getJSONArray("dropped").toString()); // [1,2] is below the ack: the server already settled it

        // A range that straddles the ack keeps only its unsettled tail.
        queue.close();
        queue = freshQueue(context);
        enqueue(queue, 1, BYTE_LIMIT, MAX_AGE_MILLIS, id(30), id(31), id(32), id(33), id(34)); // 1..4 evicted, 5 pending
        assertEquals("[[1,4]]", new JSONObject(queue.getSequenceState()).getJSONArray("dropped").toString());
        queue.deleteThroughSequence(2);
        assertEquals("[[3,4]]", new JSONObject(queue.getSequenceState()).getJSONArray("dropped").toString());
        assertEquals(1, new JSONArray(pendingJson(queue, EVENT_LIMIT)).length());
        queue.close();
    }

    private static void testV1AcknowledgementIsJournaledOnlyWhileAStreamIsOpen(Context context) throws Exception {
        AnalyticsQueue queue = freshQueue(context);
        enqueue(queue, EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS, id(40), id(41), id(42));
        queue.deleteAcknowledged(new JSONArray().put(id(40)).toString()); // no V7 stream: nothing to tell the server
        assertEquals("[]", new JSONObject(queue.getSequenceState()).getJSONArray("dropped").toString());

        queue.setStreamEpoch(3);
        queue.deleteAcknowledged(new JSONArray().put(id(41)).toString()); // delivered through V1 while a stream is open
        JSONObject state = new JSONObject(queue.getSequenceState());
        assertEquals("[[2,2]]", state.getJSONArray("dropped").toString());
        assertEquals(3L, state.getLong("stream_epoch"));
        queue.close();
    }

    private static void testBeginNewStreamForgetsTheOldEpochAndRangesBelowTheLowestRow(Context context) throws Exception {
        AnalyticsQueue queue = freshQueue(context);
        enqueue(queue, 2, BYTE_LIMIT, MAX_AGE_MILLIS, id(50), id(51), id(52), id(53)); // 1,2 evicted; 3,4 pending
        queue.setStreamEpoch(5);
        long before = new JSONObject(queue.getSequenceState()).getLong("dropped_version");

        queue.beginNewStream();
        JSONObject state = new JSONObject(queue.getSequenceState());

        assertEquals(0L, state.getLong("stream_epoch"));
        assertEquals(3L, state.getLong("stream_base"));
        assertEquals(5L, state.getLong("next_sequence"));
        assertEquals("[]", state.getJSONArray("dropped").toString());
        assertEquals(true, state.getLong("dropped_version") > before);
        assertEquals(2, new JSONArray(pendingJson(queue, EVENT_LIMIT)).length());
        queue.close();
    }

    private static void testCompactingTheDroppedJournalNeverCoversALiveRow(Context context) throws Exception {
        AnalyticsQueue queue = freshQueue(context);
        String[] ids = new String[2050];
        for (int i = 0; i < ids.length; i++) ids[i] = id(1000 + i);
        enqueue(queue, 5000, 64L * BYTE_LIMIT, MAX_AGE_MILLIS, ids); // sequences 1..2050
        queue.setStreamEpoch(1);
        JSONArray odd = new JSONArray();
        for (int i = 0; i < ids.length; i += 2) odd.put(ids[i]); // sequences 1,3,5,...: 1025 separate ranges
        queue.deleteAcknowledged(odd.toString());

        JSONArray dropped = new JSONObject(queue.getSequenceState()).getJSONArray("dropped");
        assertEquals(true, dropped.length() <= 1024);
        JSONArray pending = new JSONArray(pendingJson(queue, 5000));
        for (int i = 0; i < pending.length(); i++) {
            long sequence = pending.getJSONObject(i).getLong("sequence");
            for (int r = 0; r < dropped.length(); r++)
                assertEquals(false, sequence >= dropped.getJSONArray(r).getLong(0) && sequence <= dropped.getJSONArray(r).getLong(1));
        }
        // An ack up to the first range's end must not delete any row the queue still reports as live.
        long ack = dropped.getJSONArray(0).getLong(1);
        int live = new JSONArray(pendingJson(queue, 5000)).length();
        int deleted = queue.deleteThroughSequence(ack);
        assertEquals(live - deleted, new JSONArray(pendingJson(queue, 5000)).length());
        queue.close();
    }

    private static void testSequenceStateReportsEpochAndDroppedVersion(Context context) throws Exception {
        AnalyticsQueue queue = freshQueue(context);
        JSONObject fresh = new JSONObject(queue.getSequenceState());
        assertEquals(0L, fresh.getLong("stream_epoch"));
        assertEquals(0L, fresh.getLong("dropped_version"));
        enqueue(queue, 1, BYTE_LIMIT, MAX_AGE_MILLIS, id(60), id(61), id(62)); // two evictions: one version bump
        assertEquals(1L, new JSONObject(queue.getSequenceState()).getLong("dropped_version"));
        queue.close();
        // The epoch survives a reopen, and a credential reset forgets it (a new installation has no stream).
        queue = new AnalyticsQueue(context);
        queue.setStreamEpoch(9);
        queue.close();
        queue = new AnalyticsQueue(context);
        assertEquals(9L, new JSONObject(queue.getSequenceState()).getLong("stream_epoch"));
        queue.resetIdentity();
        assertEquals(0L, new JSONObject(queue.getSequenceState()).getLong("stream_epoch"));
        queue.close();
    }

    private static void testCountersFollowTheRowsAcrossAcksDeletesAndReopen(Context context) throws Exception {
        AnalyticsQueue queue = freshQueue(context);
        assertEquals(5, enqueue(queue, EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS, id(70), id(71), id(72), id(73), id(74)));
        assertEquals(5, queue.getState().getPendingCount());
        assertEquals(5L * (33 + 8), queue.getState().getPendingBytes());
        assertEquals(2, queue.deleteThroughSequence(2));
        assertEquals(3, queue.getState().getPendingCount());
        queue.deleteAcknowledged(new JSONArray().put(id(73)).toString());
        assertEquals(2, queue.getState().getPendingCount());
        assertEquals(2L * (33 + 8), queue.getState().getPendingBytes());
        queue.close();
        queue = new AnalyticsQueue(context);
        assertEquals(2, queue.getState().getPendingCount());
        assertEquals(6L, new JSONObject(queue.getSequenceState()).getLong("next_sequence"));
        assertEquals(3, enqueue(queue, EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS, id(75)));
        assertEquals(7L, new JSONObject(queue.getSequenceState()).getLong("next_sequence"));
        queue.clearAllPendingEvents();
        assertEquals(0, queue.getState().getPendingCount());
        assertEquals(0L, queue.getState().getPendingBytes());
        queue.close();
    }

    private static void testDuplicateEventIdDoesNotConsumeASequence(Context context) throws Exception {
        AnalyticsQueue queue = freshQueue(context);
        enqueue(queue, EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS, id(80), id(80), id(81));
        JSONArray pending = new JSONArray(pendingJson(queue, EVENT_LIMIT));
        assertEquals(2, pending.length());
        assertEquals(1L, pending.getJSONObject(0).getLong("sequence"));
        assertEquals(2L, pending.getJSONObject(1).getLong("sequence"));
        assertEquals(3L, new JSONObject(queue.getSequenceState()).getLong("next_sequence"));
        queue.close();
    }

    private static void testInvalidRecordsRollBackTheWholeBatch(Context context) throws Exception {
        AnalyticsQueue queue = freshQueue(context);
        byte[] good = frames(8, id(90));
        byte[] bad = frames(8, id(91));
        bad[4] = 7; // unknown record format
        byte[] both = new byte[good.length + bad.length];
        System.arraycopy(good, 0, both, 0, good.length);
        System.arraycopy(bad, 0, both, good.length, bad.length);
        boolean failed = false;
        try { queue.enqueueRecords(both, 2, EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS); } catch (IllegalArgumentException expected) { failed = true; }
        assertEquals(true, failed);
        assertEquals(0, queue.getState().getPendingCount());
        assertEquals(0, new JSONArray(pendingJson(queue, EVENT_LIMIT)).length());
        assertEquals(1L, new JSONObject(queue.getSequenceState()).getLong("next_sequence"));
        // the queue is still usable afterwards
        assertEquals(1, enqueue(queue, EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS, id(92)));
        queue.close();
    }

    private static void testSessionStateAndExitInfo(Context context) throws Exception {
        AnalyticsQueue queue = freshQueue(context);
        assertEquals("", queue.loadSessionState());
        queue.saveSessionState("{\"id\":\"abc\",\"active_ms\":5}");
        queue.close();
        queue = new AnalyticsQueue(context);
        assertEquals("{\"id\":\"abc\",\"active_ms\":5}", queue.loadSessionState());
        queue.resetIdentity(); // a credential reset keeps the session document
        assertEquals("{\"id\":\"abc\",\"active_ms\":5}", queue.loadSessionState());
        String exit = queue.getPreviousExitInfo(); // "" on Android < 11 or without history; otherwise parseable JSON
        if (!exit.isEmpty()) new JSONObject(exit).getInt("reason");
        queue.close();
    }

    private static void testLargeBatchesKeepOrderAndPayloadBytes(Context context) throws Exception {
        AnalyticsQueue queue = freshQueue(context);
        String[] ids = new String[300];
        for (int i = 0; i < ids.length; i++) ids[i] = id(2000 + i);
        enqueue(queue, 10000, 64L * BYTE_LIMIT, MAX_AGE_MILLIS, ids);
        byte[] data = queue.readOldest(100);
        java.nio.ByteBuffer buffer = java.nio.ByteBuffer.wrap(data);
        assertEquals(100, buffer.getInt());
        for (int i = 0; i < 100; i++) {
            assertEquals(1, (int) buffer.get());
            assertEquals((long) (i + 1), buffer.getLong());
            byte[] payload = new byte[buffer.getInt()];
            buffer.get(payload);
            assertEquals(33 + 8, payload.length);
            assertEquals((byte) 3, payload[33 + 3]);
        }
        assertEquals(0, buffer.remaining());
        queue.close();
    }

    private static AnalyticsQueue freshQueue(Context context) {
        deleteDatabaseFiles(databaseFile(context));
        return new AnalyticsQueue(context);
    }

    private static String id(int n) {
        return String.format("%08x-aaaa-4aaa-8aaa-%012x", n, n);
    }

    /** A binary event record the way the C# writer lays out its fixed header (format, event id, session id); the queue reads only the id. */
    private static byte[] record(String eventId, int tail) {
        byte[] record = new byte[33 + tail];
        record[0] = 1;
        uuidBytes(eventId, record, 1);
        uuidBytes("9be11ebf-e4f3-4696-9a47-7784061e15aa", record, 17);
        for (int i = 0; i < tail; i++) record[33 + i] = (byte) i;
        return record;
    }

    private static void uuidBytes(String uuid, byte[] destination, int offset) {
        String hex = uuid.replace("-", "");
        for (int i = 0; i < 16; i++) destination[offset + i] = (byte) Integer.parseInt(hex.substring(i * 2, i * 2 + 2), 16);
    }

    private static byte[] frames(int tail, String... eventIds) {
        java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
        for (String eventId : eventIds) {
            byte[] record = record(eventId, tail);
            out.write(record.length >>> 24); out.write(record.length >>> 16); out.write(record.length >>> 8); out.write(record.length);
            out.write(record, 0, record.length);
        }
        return out.toByteArray();
    }

    private static int enqueue(AnalyticsQueue queue, int eventLimit, long byteLimit, long maxAge, String... eventIds) {
        return queue.enqueueRecords(frames(8, eventIds), eventIds.length, eventLimit, byteLimit, maxAge);
    }

    /** readOldest decoded to the shape the assertions use: {event_id, sequence, format} (format 0 rows are the stored JSON minus install_id). */
    private static String pendingJson(AnalyticsQueue queue, int max) throws Exception {
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
