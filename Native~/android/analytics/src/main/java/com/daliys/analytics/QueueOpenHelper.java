// SQLite schema, migrations and crash-safe opening of the Android event queue database.
package com.daliys.analytics;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteException;
import android.database.sqlite.SQLiteOpenHelper;

import java.io.File;

/** Owns the queue database file: schema version, upgrades from older SDKs and recovery from a file that cannot be opened. */
final class QueueOpenHelper extends SQLiteOpenHelper {
    private static final int DATABASE_VERSION = 4;

    private QueueOpenHelper(Context context, File file) { super(context, file.getAbsolutePath(), null, DATABASE_VERSION); }

    /**
     * Opens the database. A file that cannot be opened may be a failed upgrade (full storage), not corruption: it is kept aside as
     * {@code .failed} so queued events are not destroyed with it, and a fresh database takes its place.
     */
    static QueueOpenHelper openWithRecovery(Context context, File file) {
        QueueOpenHelper helper = new QueueOpenHelper(context, file);
        try {
            helper.openWritable();
            return helper;
        } catch (SQLiteException originalFailure) {
            helper.close();
            keepFailedDatabase(file);
            deleteDatabaseFiles(file);
            QueueOpenHelper fresh = new QueueOpenHelper(context, file);
            try {
                fresh.openWritable();
                return fresh;
            } catch (SQLiteException recoveryFailure) {
                recoveryFailure.addSuppressed(originalFailure);
                throw recoveryFailure;
            }
        }
    }

    SQLiteDatabase openWritable() {
        SQLiteDatabase opened = getWritableDatabase();
        opened.enableWriteAheadLogging();
        return opened;
    }

    private static void keepFailedDatabase(File file) {
        File kept = new File(file.getAbsolutePath() + ".failed");
        if (file.exists() && (!kept.exists() || kept.delete()))
            file.renameTo(kept);
    }

    private static void deleteDatabaseFiles(File file) {
        deleteIfPresent(file);
        deleteIfPresent(new File(file.getAbsolutePath() + "-wal"));
        deleteIfPresent(new File(file.getAbsolutePath() + "-shm"));
    }

    private static void deleteIfPresent(File file) {
        if (file.exists() && !file.delete())
            throw new IllegalStateException("Could not delete corrupt analytics database file: " + file);
    }

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
