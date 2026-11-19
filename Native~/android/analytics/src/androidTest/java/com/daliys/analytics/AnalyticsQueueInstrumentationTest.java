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

import static com.daliys.analytics.QueueTestSupport.*;

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
            testStorageKeysSurviveReopenAndIdentityReset(getTargetContext());
            testCountersAreStoredInTheTransactionOfTheirBatch(getTargetContext());
            testAdoptedIdentityReplacesTheLocalOneAndKeepsTheQueue(getTargetContext());
            testZeroEventLimitAndZeroAgeMeanNoLimit(getTargetContext());
            testByteLimitCountsRowOverheadEvictsOldestAndCountsEvictions(getTargetContext());
            testStageTimersCountOnlyWhileProfilingIsOn(getTargetContext());
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
        queue.setLimits(EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS);
        try { queue.enqueueRecords(both, 2); } catch (IllegalArgumentException expected) { failed = true; }
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

    private static void testStorageKeysSurviveReopenAndIdentityReset(Context context) throws Exception {
        AnalyticsQueue queue = freshQueue(context);
        assertEquals("", queue.getMeta("v8.token"));
        queue.setMeta("v8.token", "43.kABCDEFGHIJK");
        queue.setMeta("v8.shapes", "{\"project_id\":\"p\",\"shapes\":[]}");
        queue.close();
        queue = new AnalyticsQueue(context);
        assertEquals("43.kABCDEFGHIJK", queue.getMeta("v8.token"));
        queue.resetIdentity();                                  // a credential reset must not lose the V8 state or the counters
        assertEquals("43.kABCDEFGHIJK", queue.getMeta("v8.token"));
        assertEquals("{\"project_id\":\"p\",\"shapes\":[]}", queue.getMeta("v8.shapes"));
        for (String bad : new String[]{"install_id", "installation_credential", "stream_epoch", "v8." + new String(new char[40]).replace('\0', 'x')}) {
            try { queue.getMeta(bad); throw new AssertionError("reading " + bad + " must be refused"); } catch (IllegalArgumentException expected) { /* ok */ }
            try { queue.setMeta(bad, "x"); throw new AssertionError("writing " + bad + " must be refused"); } catch (IllegalArgumentException expected) { /* ok */ }
        }
        queue.close();
    }

    private static void testCountersAreStoredInTheTransactionOfTheirBatch(Context context) throws Exception {
        AnalyticsQueue queue = freshQueue(context);
        assertEquals("", queue.getMeta("counters"));
        try {                                                   // the bounds come first: a queue without limits refuses to store
            queue.enqueueRecords(frames(8, id(6999)), 1, "{\"attempt\":1}");
            throw new AssertionError("enqueue before setLimits must be refused");
        } catch (IllegalStateException expected) { /* ok */ }
        assertEquals("", queue.getMeta("counters"));
        queue.setLimits(EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS);
        queue.enqueueRecords(frames(8, id(7000)), 1, "{\"attempt\":5}");
        assertEquals("{\"attempt\":5}", queue.getMeta("counters"));
        queue.enqueueRecords(frames(8, id(7001)), 1, null);        // null leaves the stored counters alone
        assertEquals("{\"attempt\":5}", queue.getMeta("counters"));
        try {                                                   // a rejected batch must not store its counters either
            queue.enqueueRecords(new byte[]{0, 0, 0, 2, 9, 9}, 1, "{\"attempt\":99}");
            throw new AssertionError("an invalid record must be refused");
        } catch (IllegalArgumentException expected) { /* ok */ }
        assertEquals("{\"attempt\":5}", queue.getMeta("counters"));
        queue.close();
        queue = new AnalyticsQueue(context);
        assertEquals("{\"attempt\":5}", queue.getMeta("counters"));
        queue.resetIdentity();
        assertEquals("{\"attempt\":5}", queue.getMeta("counters"));
        queue.close();
    }

    private static void testAdoptedIdentityReplacesTheLocalOneAndKeepsTheQueue(Context context) throws Exception {
        AnalyticsQueue queue = freshQueue(context);
        enqueue(queue, EVENT_LIMIT, BYTE_LIMIT, MAX_AGE_MILLIS, id(7100), id(7101));
        String sequenceBefore = queue.getSequenceState();
        String adopted = "6f1c9b0e-2d44-4f6a-9a31-0c5d7e8b9a10";
        String credential = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQ";   // 43 characters
        queue.adoptIdentity(adopted, credential);
        assertEquals(adopted, queue.getState().getInstallationId());
        assertEquals(credential, queue.getState().getInstallationCredential());
        assertEquals(2, queue.getState().getPendingCount());
        assertEquals(new JSONObject(sequenceBefore).getLong("next_sequence"), new JSONObject(queue.getSequenceState()).getLong("next_sequence"));
        queue.close();
        queue = new AnalyticsQueue(context);
        assertEquals(adopted, queue.getState().getInstallationId());
        try { queue.adoptIdentity("not-a-uuid", credential); throw new AssertionError("a bad id must be refused"); } catch (IllegalArgumentException expected) { /* ok */ }
        try { queue.adoptIdentity(adopted, "short"); throw new AssertionError("a bad credential must be refused"); } catch (IllegalArgumentException expected) { /* ok */ }
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

    private static void testZeroEventLimitAndZeroAgeMeanNoLimit(Context context) throws Exception {
        AnalyticsQueue queue = new AnalyticsQueue(context);
        queue.clearAllPendingEvents();
        String[] ids = new String[300];
        for (int i = 0; i < ids.length; i++) ids[i] = id(9000 + i);
        int droppedBefore = new JSONObject(queue.getSequenceState()).getJSONArray("dropped").length();   // clearing the queue above journaled its old rows
        long evictedBefore = longOf(queue.getMeta("evicted_total"));
        enqueue(queue, 0, BYTE_LIMIT, 0, ids);                      // 0 = no limit by count, 0 = events never expire
        assertEquals(300, queue.getState().getPendingCount());
        assertEquals(droppedBefore, new JSONObject(queue.getSequenceState()).getJSONArray("dropped").length());
        assertEquals(evictedBefore, longOf(queue.getMeta("evicted_total")));
        boolean failed = false;
        try { enqueue(queue, -1, BYTE_LIMIT, 0, id(9500)); } catch (IllegalArgumentException expected) { failed = true; }
        assertTrue(failed);
        failed = false;
        try { enqueue(queue, 0, BYTE_LIMIT, -1, id(9501)); } catch (IllegalArgumentException expected) { failed = true; }
        assertTrue(failed);
        queue.close();
    }

    private static void testByteLimitCountsRowOverheadEvictsOldestAndCountsEvictions(Context context) throws Exception {
        AnalyticsQueue queue = new AnalyticsQueue(context);
        queue.clearAllPendingEvents();
        long before = longOf(queue.getMeta("evicted_total"));
        // a record is 33 + 8 bytes; with the 40 bytes of row overhead every event costs 81: a limit of 810 holds exactly ten
        String[] ids = new String[25];
        for (int i = 0; i < ids.length; i++) ids[i] = id(9600 + i);
        enqueue(queue, 0, 810, 0, ids);
        assertEquals(10, queue.getState().getPendingCount());
        JSONArray pending = new JSONArray(pendingJson(queue, 100));
        assertEquals(ids[15], pending.getJSONObject(0).getString("event_id"));  // the oldest fifteen went
        assertEquals(15L, longOf(queue.getMeta("evicted_total")) - before);
        queue.close();
    }

    private static void testStageTimersCountOnlyWhileProfilingIsOn(Context context) throws Exception {
        AnalyticsQueue queue = new AnalyticsQueue(context);
        queue.clearAllPendingEvents();
        enqueue(queue, 0, BYTE_LIMIT, 0, id(9700));
        assertEquals("{}", queue.getProfile());                            // off by default: nothing recorded
        queue.setProfiling(true);
        String[] ids = new String[10];
        for (int i = 0; i < ids.length; i++) ids[i] = id(9710 + i);
        enqueue(queue, 0, BYTE_LIMIT, 0, ids);
        queue.readOldest(5);
        JSONObject profile = new JSONObject(queue.getProfile());
        assertEquals(1L, profile.getJSONArray("enq.total").getLong(0));
        assertEquals(10L, profile.getJSONArray("enq.insert_exec").getLong(0));
        assertEquals(1L, profile.getJSONArray("enq.commit").getLong(0));
        assertEquals(1L, profile.getJSONArray("read.total").getLong(0));
        assertTrue(profile.getJSONArray("enq.total").getLong(1) > 0);      // wall time
        queue.setProfiling(false);                                         // turning it off clears the numbers
        assertEquals("{}", queue.getProfile());
        queue.close();
    }
}
