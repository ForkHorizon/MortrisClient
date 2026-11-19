## A4 — журнал последовательностей и миграция

ID: A4-1  
Серьёзность: высоко  
Уверенность: подтверждено чтением кода  
Место: `Native~/android/analytics/src/main/java/com/daliys/analytics/AnalyticsQueue.java:102–111, 406–420`  
Что не так: `beginNewStream()` и `newIdentity()` удаляют весь журнал пропусков, сохраняя строки с их прежними sequence. Если между ожидающими строками есть пропуск, новый поток сообщает его серверу как непропущенный номер.  
Сценарий: в очереди остаются события с sequence 20 и 22, а 21 записан как отброшенный диапазон. Затем вызывается `beginNewStream()` или `resetIdentity()`. Очередь оставляет строки 20 и 22, очищает журнал и сообщает `stream_base=20`, `next_sequence=23`, `dropped=[]`. Серверу не сообщается, что 21 был отброшен.  
Цитата кода:
```java
102    public synchronized void beginNewStream() {
105        long next = nextSequence;
106        long base = android.database.DatabaseUtils.longForQuery(database,
107                "SELECT COALESCE(MIN(sequence), ?) FROM pending_events", new String[]{Long.toString(next)});
108        putMetadata(META_STREAM_BASE, Long.toString(base));
109        putMetadata(META_STREAM_EPOCH, "0");
110        database.delete("dropped_ranges", null, null);
```
При сбросе identity та же очистка происходит в `newIdentity()`, а строки очереди сохраняют прежние номера. Контракт описывает `dropped` как перечень локально отброшенных последовательностей (строки 75–88).  
Как исправить (кратко): передавать в новый поток сохранившиеся пропуски между оставшимися строками либо перенумеровать строки и согласованно обновить связанные счётчики.

ID: A4-2  
Серьёзность: средне  
Уверенность: вероятно  
Место: `Native~/android/analytics/src/main/java/com/daliys/analytics/AnalyticsQueue.java:321–333, 554–560`  
Что не так: обработчик восстановления удаляет файлы базы при любом `SQLiteException` во время открытия. Версия 4 копирует все ожидающие строки во временную таблицу при миграции; если копирование падает, например из-за нехватки места, попытка восстановления может удалить исходную базу вместе с очередью.  
Сценарий: приложение открывает существующую базу для перехода на схему v4; миграция не помещается на диске и выбрасывает `SQLiteException`; `openDatabaseWithRecovery()` удаляет основную базу и WAL/SHM, после чего создаёт пустую.  
Цитата кода:
```java
321    private SQLiteDatabase openDatabaseWithRecovery() {
322        try {
323            return openDatabase();
324        } catch (android.database.sqlite.SQLiteException originalFailure) {
325            helper.close();
326            deleteDatabaseFiles();
327            helper = new QueueOpenHelper(context, databaseFile.getAbsolutePath());
328            try {
329                return openDatabase();
330            } catch (android.database.sqlite.SQLiteException recoveryFailure) {
331                recoveryFailure.addSuppressed(originalFailure);
332                throw recoveryFailure;
```
Миграция копирует строки и заменяет таблицу:
```java
556    createPendingTable(database, "pending_events_v4");
557    database.execSQL("INSERT INTO pending_events_v4 ... "
558            + "SELECT ... FROM pending_events");
559    database.execSQL("DROP TABLE pending_events");
560    database.execSQL("ALTER TABLE pending_events_v4 RENAME TO pending_events");
```
Как исправить (кратко): удалять базу только после подтверждения повреждения; ошибки миграции или открытия из-за ресурсов возвращать вызывающему коду, сохранив исходные файлы.

## Улучшения (необязательные)

- Добавить проверку на разреженные sequence при сбросе потока, чтобы такие пропуски не исчезали незаметно.

## Проверено, замечаний нет

- Миграции v1/v2/v3→v4: добавление `attempt_count`, создание `dropped_ranges`, сохранение JSON-строк как format 0 и перенос `row_id`.
- `deleteThroughSequence()` и `deleteAcknowledged()`: удаление подтверждённых строк и обработка диапазонов, пересекающих `ackThrough`.
- `ensureIdentity()` и сохранение `session_state` при `resetIdentity()`.
- Повреждённая база: восстановление удаляет также `-wal` и `-shm`; замечание A4-2 относится к тому, что этот путь срабатывает и при иных ошибках открытия.

Файлы отчёта не создавал: по правилам этой подзадачи это read-only аудит.
