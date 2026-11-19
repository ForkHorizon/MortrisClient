ID: A7-1  
Серьёзность: средне  
Уверенность: подтверждено чтением кода  
Место: `Runtime/Internal/AndroidQueueBridge.cs:124–127, 149–153`; `Runtime/Internal/AnalyticsPersistenceWorker.cs:85–96, 184)  
Что не так: Кэш `_pending` обновляется несогласованно, если запись с главного потока пересекается с удалением подтверждённых строк в рабочем потоке. Java сериализует операции очереди, но C# применяет их результаты уже после возврата из Java; `Volatile.Write` может затереть более позднее изменение от `Interlocked.Add`.  
Сценарий: рабочий поток читает пачку и загружает её; `PersistNow` добавляет запись, Java возвращает новый счётчик, но главный поток ещё не успел записать его в `_pending`; загрузка подтверждается, и `DeleteAcknowledged` уменьшает старый кэш; затем `EnqueueRecords` записывает ранее полученное значение. Очередь уже пуста, а `PendingCount` остаётся положительным, что может нарушить решение загрузчика о достижении порога.  
Цитата кода:
```csharp
public void EnqueueRecords(...) =>
    Volatile.Write(ref _pending, _lowLevel
        ? EnqueueLowLevel(...)
        : _queue.Call<int>("enqueueRecords", ...));

var deleted = _queue.Call<int>("deleteAcknowledged", eventIdsJson);
Interlocked.Add(ref _pending, -deleted);
```
`PersistNow` выполняет запись под `_writeSync`, но загрузчик вызывается уже после выхода из этой блокировки:
```csharp
lock (_writeSync) { ... WriteBuffer(); ... }
var upload = _uploader.Flush(_bridge, HasFlushWaiters());
```
Как исправить (кратко): Синхронизировать все изменения кэша счётчика одним замком либо получать актуальный счётчик из результата каждой операции без перезаписи устаревшим значением.

ID: A7-2  
Серьёзность: низко  
Уверенность: подтверждено чтением кода  
Место: `Runtime/Internal/AndroidQueueBridge.cs:73–78, 175–178)  
Что не так: `NewGlobalRef(local)` сохраняет глобальную ссылку на класс, но ссылка не сохраняется в поле и не освобождается в `Dispose`.  
Сценарий: при каждом создании и освобождении `AndroidQueueBridgeInstance` глобальная ссылка на класс остаётся в JVM; повторные инициализации накапливают ссылки.  
Цитата кода:
```csharp
var local = AndroidJNI.GetObjectClass(_handle);
var type = AndroidJNI.NewGlobalRef(local);
AndroidJNI.DeleteLocalRef(local);
_enqueueId = AndroidJNI.GetMethodID(type, "enqueueRecords", "([BIIJJ)I");
_readId = AndroidJNI.GetMethodID(type, "readOldest", "(I)[B");
...
public void Dispose()
{
    _queue.Dispose();
}
```
Как исправить (кратко): Сохранить глобальную ссылку в поле и вызвать `DeleteGlobalRef` при освобождении моста.

**Проверено, замечаний нет:** сигнатуры JNI `enqueueRecords` (`([BIIJJ)I`) и `readOldest` (`(I)[B`) совпадают с Java-методами; локальные ссылки на byte arrays освобождаются в `finally`; исключения Java после низкоуровневых вызовов очищаются; рабочий поток прикрепляется к JVM и отсоединяется; `getPreviousExitInfo` ограничен Android API 30+, при `minSdk 25` возвращает пустую строку на более старых версиях. Общие массивы аргументов используются в сериализованном пути записи и отдельном пути чтения; независимой гонки этих массивов по прочитанным вызовам не подтвердил.
