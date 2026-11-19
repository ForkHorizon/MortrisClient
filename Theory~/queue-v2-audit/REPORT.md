# Аудит queue-v2: поиск ошибок

## Краткая сводка

- Критично: 0; высоко: 2; средне: 7; низко: 3.
- Очистка очереди при отключении сбора может опоздать до текущего upload, и событие успеет уйти.
- При создании нового V7 stream удаляются внутренние dropped ranges, хотя sequence строк остаются прежними.
- Ошибка миграции v3→v4 может привести к удалению исходной БД вместе с очередью.
- Восстановление завершённой сессии может записать повторный `sys_session_end` при аварии между записью события и snapshot.
- Одиночная повреждённая строка может блокировать отправку всей очереди.

Область сравнения: изменения `8ad86d7..5cc7b57`; требуемый снимок реализации — `5cc7b57`. Все серьёзные находки ниже сверены с кодом этого снимка.

## Находки

### Высокая серьёзность

#### A1-1 — очередь может отправить события после запроса очистки

**Уверенность:** подтверждено чтением кода  
**Место:** `Runtime/Internal/AnalyticsPersistenceWorker.cs:74-79, 171-184, 202-207`  
**Что не так:** `ClearPending()` очищает буфер и выставляет флаг очистки, но не ждёт текущего worker. Worker проверяет флаг один раз внутри цикла записи, а затем вызывает uploader без повторной проверки.  
**Сценарий:** worker уже прошёл проверку `_clearRequested`, когда вызывается `SetCollectionEnabled(false, true)`; durable очередь всё ещё содержит события, и загрузка due либо достигла порога; worker отправляет их, а очистка произойдёт только в следующем цикле.  
**Цитата кода:**
```csharp
if (Interlocked.Exchange(ref _clearRequested, 0) == 1)
    _bridge.ClearAllPendingEvents();
WriteBuffer();
...
var upload = _uploader.Flush(_bridge, HasFlushWaiters());
```
**Как исправить (кратко):** сериализовать очистку с загрузкой и проверять запрос очистки перед любым upload.

#### A4-2 — ошибка миграции может удалить исходную очередь

**Уверенность:** вероятно  
**Место:** `Native~/android/analytics/src/main/java/com/daliys/analytics/AnalyticsQueue.java:321-333, 554-560`  
**Что не так:** восстановление удаляет файлы БД после любого `SQLiteException` при открытии. Новая миграция v3→v4 копирует все строки; если она падает по причине ресурсов, например нехватки места, общий обработчик может удалить старую базу и вместе с ней ожидающие события.  
**Сценарий:** открывается v3 БД; копирование в `pending_events_v4` выбрасывает `SQLiteException`; `openDatabaseWithRecovery()` закрывает helper и удаляет базу/WAL/SHM перед повторным открытием.  
**Цитата кода:**
```java
} catch (android.database.sqlite.SQLiteException originalFailure) {
    helper.close();
    deleteDatabaseFiles();
    helper = new QueueOpenHelper(context, databaseFile.getAbsolutePath());
    try {
        return openDatabase();
```
```java
createPendingTable(database, "pending_events_v4");
database.execSQL("INSERT INTO pending_events_v4 ... SELECT ... FROM pending_events");
database.execSQL("DROP TABLE pending_events");
database.execSQL("ALTER TABLE pending_events_v4 RENAME TO pending_events");
```
**Как исправить (кратко):** отличать повреждённую базу от ошибки миграции/ресурсов и не удалять исходную очередь при неуспешном обновлении схемы.

### Средняя серьёзность

#### A4-1 — новый stream теряет внутренние dropped ranges

**Уверенность:** подтверждено чтением кода  
**Место:** `Native~/android/analytics/src/main/java/com/daliys/analytics/AnalyticsQueue.java:102-111, 406-420`  
**Что не так:** `beginNewStream()` и `newIdentity()` очищают весь журнал пропусков, сохраняя оставшиеся строки с их прежними sequence. Если пропуск находится между ещё ожидающими строками, новый stream не сообщает серверу, что этот номер закрыт.  
**Сценарий:** pending строки имеют sequence 20 и 22, sequence 21 удалён и записан в dropped journal; затем вызывается `beginNewStream()`; журнал стирается, база сообщает диапазон 20..22 без dropped 21, поэтому подтверждение потока может остановиться на дыре.  
**Цитата кода:**
```java
long base = DatabaseUtils.longForQuery(database,
        "SELECT COALESCE(MIN(sequence), ?) FROM pending_events", ...);
putMetadata(META_STREAM_BASE, Long.toString(base));
putMetadata(META_STREAM_EPOCH, "0");
database.delete("dropped_ranges", null, null);
```
**Как исправить (кратко):** сохранять внутренние пропуски при переоткрытии stream либо согласованно перенумеровывать оставшиеся строки.

#### A1-2 — после ошибки записи автоматическая повторная попытка не ставится

**Уверенность:** подтверждено чтением кода  
**Место:** `Runtime/Internal/AnalyticsPersistenceWorker.cs:212-225, 187-207`  
**Что не так:** при исключении `WriteBuffer()` возвращает события в буфер, но worker ставит статус `PersistenceFailed`; финализатор не планирует новый worker и не вооружает flush timer для этого статуса.  
**Сценарий:** временная ошибка Java/диска при записи одной небольшой пачки → записи восстанавливаются в памяти → больше событий не приходит и нет явного `FlushAsync`/lifecycle вызова → очередь сама не повторяет запись; последующий crash теряет события независимо от прошедших 200 мс.  
**Цитата кода:**
```csharp
catch
{
    _buffer.Restore(frames, count);
    throw;
}
...
status = FlushStatus.PersistenceFailed;
...
if (status != FlushStatus.PersistenceUnavailable && status != FlushStatus.PersistenceFailed)
{
    ...
}
```
**Как исправить (кратко):** после временной ошибки записи планировать ограниченную повторную попытку, сохраняя текущую буферизацию.

#### A2-1 — fractional decimal теряет точность на новом пути

**Уверенность:** подтверждено чтением кода  
**Место:** `Runtime/Internal/Transport/EventRecord.cs:198-209, 229, 431`; старый сериализатор: `Runtime/Internal/PersistenceEventSerializer.cs:87-94` на `8ad86d7`  
**Что не так:** дробный `decimal` разбирается как `double`, а V1 затем выводит round-trip текст double. Старый сериализатор выводил decimal напрямую как `IFormattable`, сохраняя его точное десятичное значение.  
**Сценарий:** игра передаёт `0.12345678901234567890m` → бинарная запись хранит ближайший double → V1 payload содержит округлённое число.  
**Цитата кода:**
```csharp
AddRawDouble(key, double.Parse(lexeme, NumberStyles.Float, CultureInfo.InvariantCulture));
case decimal m: AddLexeme(key, m.ToString(CultureInfo.InvariantCulture)); break;
case EventRecordFormat.TagDouble: json.Append(p.D.ToString("R", CultureInfo.InvariantCulture)); break;
```
**Как исправить (кратко):** сохранить дробный decimal точным или выделить точное представление для V1; оговорённый переход больших целых decimal в double эту дробную потерю не покрывает.

#### A2-3 — одна повреждённая запись блокирует очередь

**Уверенность:** подтверждено чтением кода  
**Место:** `Runtime/Internal/Transport/EventRecord.cs:546-569`; `Runtime/Internal/AndroidQueueBridge.cs:141`; `Runtime/Internal/AnalyticsUploader.cs:204-213, 271-273`  
**Что не так:** `QueueBatch.FromFrame` разбирает каждый row перед возвратом batch и бросает `FormatException` для повреждённого format 0 JSON или неизвестного формата. Uploader ловит исключение общим backoff, но не удаляет/изолирует строку, поэтому следующий read снова начинает с неё.  
**Сценарий:** в БД есть повреждённая старая JSON-строка перед корректными rows → `readOldest` возвращает её первой → парсер падает → uploader откладывает попытку → строка остаётся на месте и снова блокирует пакет.  
**Цитата кода:**
```csharp
else if (format == 0)
{
    var json = MiniJson.Parse(... ) as Dictionary<string, object>
        ?? throw new FormatException("Queued payload is not an object.");
    var record = EventRecordJson.FromJson(json, out _);
}
...
catch (Exception)
{
    return BackOff(now, null);
}
```
**Как исправить (кратко):** определить отдельную политику для нечитаемой строки, чтобы она не удерживала всю очередь.

#### A3-1 — сбой SQLite commit оставляет Java-кэши в неопределённом состоянии

**Уверенность:** вероятно  
**Место:** `Native~/android/analytics/src/main/java/com/daliys/analytics/AnalyticsQueue.java:198-215, 150-164`  
**Что не так:** `enqueueRecords` обновляет `pendingCount`, `pendingBytes` и локальный sequence до фиксации; `committed` становится true до `endTransaction()`. Если commit внутри `endTransaction()` бросает исключение, выполнение не доходит до `reloadCaches()`. `resetIdentity()` аналогично меняет поле `identity` внутри транзакции и не перечитывает его при исключении из фиксации.  
**Сценарий:** SQLite откатывает неудачный commit → БД сохраняет прежние строки/метаданные, а Java объект продолжает с кэшированными значениями из незафиксированной транзакции; следующая запись может пропустить sequence или вернуть неверный pending count/identity.  
**Цитата кода:**
```java
pendingCount++;
pendingBytes += length;
...
database.setTransactionSuccessful();
committed = true;
} finally {
    database.endTransaction();
    if (!committed) reloadCaches();
}
```
```java
identity = newIdentity(next);
database.setTransactionSuccessful();
} finally {
    database.endTransaction();
}
reloadCaches();
```
**Как исправить (кратко):** считать поля окончательными только после успешного `endTransaction()` и перечитывать все кэши/identity при ошибке commit.

#### A6-1 — перевод системных часов меняет решение о таймауте сессии

**Уверенность:** подтверждено чтением кода  
**Место:** `Runtime/Internal/Session/SessionTracker.cs:71-96, 211-218`  
**Что не так:** разница между уходом и возвратом измеряется разностью UTC wall-clock миллисекунд. Перевод системного времени вперёд может ложно превысить `SessionTimeout`, назад — скрыть уже прошедший таймаут. Смена только часового пояса сама по себе Unix time не меняет.  
**Сценарий:** игрок уходит на 10 секунд; часы переводят вперёд на сутки; при возврате вычисленный `gap` больше таймаута, и SDK закрывает сессию как `timeout` и начинает новую.  
**Цитата кода:**
```csharp
var now = _nowMs();
...
var left = _backgroundAt; var gap = Math.Max(0, now - left);
if (gap >= (long)_timeout.TotalMilliseconds)
{
    EmitSessionEnd(left, "timeout", true);
```
**Как исправить (кратко):** использовать монотонные часы для длительностей, сохраняя UTC только для event timestamps.

#### A6-2 — восстановленный конец сессии может задублироваться при crash

**Уверенность:** подтверждено чтением кода  
**Место:** `Runtime/Internal/AnalyticsPersistenceWorker.cs:169-182, 235-244`; `Runtime/Internal/Session/SessionTracker.cs:142-182`  
**Что не так:** recovery end записывается в очередь отдельно от snapshot новой сессии. Между успешной записью очереди и `SaveSessionState` процесс может умереть; при следующем запуске старый snapshot повторно вызывает `Recover`. Новый `event_id` генерируется при каждом вызове `Write`.  
**Сценарий:** процесс B восстанавливает session A и сохраняет её `sys_session_end` в очередь; B завершается до сохранения нового snapshot; процесс C загружает прежнее состояние A и вставляет второй end с другим ID.  
**Цитата кода:**
```csharp
RecoverPreviousSession();
...
WriteBuffer();
...
SaveSessionState(false);
```
**Как исправить (кратко):** фиксировать recovery marker и end в одной транзакции либо использовать стабильный idempotency key для recovery-события.

### Низкая серьёзность

#### A2-2 — varint reader принимает переполнение десятого байта

**Уверенность:** подтверждено чтением кода  
**Место:** `Runtime/Internal/Transport/EventRecord.cs:32-42`  
**Что не так:** последний байт ulong varint не ограничен значением 0/1; старшие биты теряются при 64-битном сдвиге, и повреждённое значение может быть принято как другое число.  
**Сценарий:** повреждённое поле `TagUInt64` содержит девять байтов `0x80`, затем `0x02`; reader возвращает ноль вместо ошибки формата. Это требует повреждённого локального blob, обычный writer такого varint не создаёт.  
**Цитата кода:**
```csharp
for (var shift = 0; shift < 70; shift += 7)
{
    if (position >= end) throw new FormatException("Event record is truncated.");
    var b = buffer[position++];
    result |= (ulong)(b & 127) << shift;
    if (b < 128) return result;
}
```
**Как исправить (кратко):** на десятой позиции разрешать только младший бит.

#### A7-1 — C# PendingCount может отстать от Java queue

**Уверенность:** подтверждено чтением кода  
**Место:** `Runtime/Internal/AndroidQueueBridge.cs:124-127, 149-153`; `Runtime/Internal/AnalyticsPersistenceWorker.cs:85-96, 184`  
**Что не так:** запись enqueue публикует абсолютный count через `Volatile.Write`, а ack уменьшает его через `Interlocked.Add`; это не одна сериализованная операция в C#. Загрузка выполняется вне `_writeSync`, поэтому она может пересечься с `PersistNow`.  
**Сценарий:** enqueue в Java возвращает count=2 и приостанавливается до volatile write; upload подтверждает и удаляет одну строку, уменьшая старый кэш до 0; enqueue затем записывает 2, хотя в Java осталась 1. Решения о пороге загрузки используют неверный кэш до следующего `GetState()`.  
**Цитата кода:**
```csharp
Volatile.Write(ref _pending, _queue.Call<int>("enqueueRecords", ...));
...
var deleted = _queue.Call<int>("deleteAcknowledged", eventIdsJson);
Interlocked.Add(ref _pending, -deleted);
```
**Как исправить (кратко):** сериализовать все изменения C# кэша одним lock или обновлять его согласованно от актуального результата каждой queue операции.

#### A7-2 — глобальная JNI ссылка на класс не освобождается

**Уверенность:** подтверждено чтением кода  
**Место:** `Runtime/Internal/AndroidQueueBridge.cs:73-78, 175-178`  
**Что не так:** `NewGlobalRef(local)` создаёт глобальную ссылку, но она не сохраняется для последующего `DeleteGlobalRef`. Повторные создания моста оставляют ссылки в JVM до завершения процесса.  
**Сценарий:** повторная инициализация/создание моста → ссылка на класс не освобождается в `Dispose()`. Обычная production-инициализация singleton ограничивает частоту этого пути.  
**Цитата кода:**
```csharp
var local = AndroidJNI.GetObjectClass(_handle);
var type = AndroidJNI.NewGlobalRef(local);
AndroidJNI.DeleteLocalRef(local);
...
public void Dispose()
{
    _queue.Dispose();
}
```
**Как исправить (кратко):** хранить global ref в поле и удалять при Dispose.

## Отклонено при перепроверке

- Предварительное подозрение, что `mergeOldestDroppedRanges()` оставляет живые строки между объединяемыми диапазонами: не подтверждено в снимке `5cc7b57`. В строках 491–494 уже удаляются pending rows внутри расширяемого диапазона; Android-тест `testCompactingTheDroppedJournalNeverCoversALiveRow` покрывает этот сценарий.
- Повторная регистрация после 401 V7 может повторять запросы при повторном 401, но этот путь присутствует уже в базе `8ad86d7`, поэтому не является регрессией queue-v2.
- Отклонение `sys_app_foreground` и `sys_session_end` сервером не рассматривается как дефект SDK: ограничение явно описано в `Documentation/ServerContractLifecycle.md`.

## Улучшения

- Для сохранения данных при ошибке миграции полезно разделять recovery повреждённой SQLite БД и временные ошибки открытия/обновления схемы.
- Для таймаутов сессий полезно явно разделять монотонную длительность и UTC timestamp.

## Что не удалось проверить без запуска

- Не проверялось фактическое поведение Android SQLite при ошибке commit и при нехватке места во время v3→v4 миграции; подходящие проверки — инструментальные тесты с fault injection и заполненным хранилищем.
- Межпоточные окна очистки и C# `PendingCount` подтверждены порядком операций в коде, но не воспроизводились планировщиком; проверить их следует детерминированными барьерами в concurrency tests.
- Поведение таймера после сбоя JNI/диска не запускалось; проверка должна внести одноразовый отказ enqueue и подтвердить автоматическую повторную попытку без новых событий.
- Телефон и Unity/IL2CPP не запускались; это ограничение из задания и не влияет на чтение приведённых веток.

## Покрытие

- Рабочий поток/таймеры: `AnalyticsPersistenceWorker.cs`, `AnalyticsRuntime.cs`, `Analytics.cs`, `AnalyticsLifecycle.cs`.
- Записи/валидатор: `EventBuffer.cs`, `EventRecord.cs`, `EventValidator.cs`, старый `PersistenceEventSerializer.cs` из `8ad86d7`.
- Java очередь: `AnalyticsQueue.java` — enqueue/read, счётчики, sequence/dropped journal, identity, миграция и recovery.
- Отправка/JNI: `AnalyticsUploader.cs`, `V7Session.cs`, `AndroidQueueBridge.cs`, точки вызова очереди.
- Сессии: `SessionTracker.cs`, `AnalyticsOptions.cs`, lifecycle callbacks.
- V7 совместимость: `M7Event.cs`, `M7EventEncoder.cs`, `M7Catalog.cs`, `M7Columns.cs`, `M7Aliases.cs`, `add_lifecycle_shapes.py`, `Documentation/ServerContractLifecycle.md`.
- Документы замысла: `EventPipelineAndSessions.md`, `ServerContractLifecycle.md`, `DESIGN_QUEUE_V2.md`, `ANALYSIS.md`, `V7Transport.md`.
- Суб-агенты также читали тестовые файлы и серверные контракты; ничего не запускалось. Отдельно не проверялись все тестовые assertions и runtime поведение на устройствах.

## Метаданные

- Суб-агентов использовано: 8.
- Аудит выполнен по запросу для `8ad86d7..5cc7b57`; HEAD на момент работы: `5d1207332ca08616771be8dac4293d5de9c073d7`.
- Сборки, тесты, эмуляторы, Unity, Gradle, dotnet, adb и сервер не запускались.
