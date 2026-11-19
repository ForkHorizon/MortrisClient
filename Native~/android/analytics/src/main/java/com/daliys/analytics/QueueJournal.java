// Metadata rows and the dropped-range journal of the Android event queue (sequences the server must not wait for).
package com.daliys.analytics;

import android.content.ContentValues;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;

/** Key/value metadata and the journal of locally dropped sequence ranges, on the queue's database; callers hold the queue lock. */
final class QueueJournal {
    static final String DROPPED_VERSION = "dropped_version";
    /** Older ranges are merged beyond this bound; a wider skip is safe because skips only mean "do not wait for". */
    private static final int MAX_DROPPED_RANGES = 1024;

    private final SQLiteDatabase database;

    QueueJournal(SQLiteDatabase database) { this.database = database; }

    /** Journals the sequences of rows about to be deleted without acknowledgement. */
    void recordWhere(String where, String[] args) {
        try (Cursor cursor = database.query("pending_events", new String[]{"sequence"}, where, args,
                null, null, "sequence ASC")) {
            boolean any = false;
            while (cursor.moveToNext()) { record(cursor.getLong(0)); any = true; }
            if (any) bumpVersion();
        }
    }

    void bumpVersion() {
        put(DROPPED_VERSION, Long.toString(getLong(DROPPED_VERSION, 0) + 1));
    }

    long getLong(String key, long fallback) {
        String value = get(key);
        return value == null ? fallback : Long.parseLong(value);
    }

    void record(long sequence) {
        ContentValues extend = new ContentValues();
        extend.put("to_sequence", sequence);
        if (database.update("dropped_ranges", extend, "to_sequence = ?", new String[]{Long.toString(sequence - 1)}) > 0)
            return;
        ContentValues range = new ContentValues();
        range.put("from_sequence", sequence);
        range.put("to_sequence", sequence);
        database.insertWithOnConflict("dropped_ranges", null, range, SQLiteDatabase.CONFLICT_IGNORE);
        if (android.database.DatabaseUtils.queryNumEntries(database, "dropped_ranges") > MAX_DROPPED_RANGES)
            mergeOldest();
    }

    private void mergeOldest() {
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

    long[][] ranges() {
        try (Cursor cursor = database.query("dropped_ranges", new String[]{"from_sequence", "to_sequence"}, null,
                null, null, null, "from_sequence ASC")) {
            long[][] ranges = new long[cursor.getCount()][];
            int index = 0;
            while (cursor.moveToNext()) ranges[index++] = new long[]{cursor.getLong(0), cursor.getLong(1)};
            return ranges;
        }
    }

    String get(String key) {
        try (Cursor cursor = database.query("metadata", new String[]{"value"}, "key = ?", new String[]{key}, null, null, null)) {
            return cursor.moveToFirst() ? cursor.getString(0) : null;
        }
    }
    String require(String key) { String value = get(key); if (value == null) throw new IllegalStateException("Missing metadata: " + key); return value; }
    void put(String key, String value) { ContentValues row = new ContentValues(); row.put("key", key); row.put("value", value); database.insertWithOnConflict("metadata", null, row, SQLiteDatabase.CONFLICT_REPLACE); }
}
