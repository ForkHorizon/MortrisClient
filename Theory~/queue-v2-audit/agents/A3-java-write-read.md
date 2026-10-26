## A3 — аудит очереди Java

### A3-1

- **Severity:** high
- **Confidence:** probable (по чтению кода)
- **Место:** `Native~/android/analytics/src/main/java/com/daliys/analytics/AnalyticsQueue.java:198–215`
- **Проблема:** кэши счётчиков и `nextSequence` обновляются до фиксации транзакции. Флаг `committed` устанавливается до `database.endTransaction()`, а перезагрузка кэшей выполняется только если он `false`. Если фиксация транзакции завершится ошибкой, БД откатится, но Java-объект сохранит значения из незакоммиченной записи.
- **Сценарий:** при ошибке SQLite во время commit вставленные строки и `META_NEXT_SEQUENCE` не сохранятся. Следующая вставка использует уже увеличенный `nextSequence`; из-за незаписанной последовательности сервер может ждать пропущенный номер. `pendingCount` и `pendingBytes` также могут не совпадать с БД и повлиять на `enforceBounds`.
- **Цитата:**
  ```java
  198 if (insert.executeInsert() != -1L) {
  199     sequence++;
  200     pendingCount++;
  201     pendingBytes += length;
  ...
  205 if (sequence != nextSequence) {
  206     putMetadata(META_NEXT_SEQUENCE, Long.toString(sequence));
  207     nextSequence = sequence;
  ...
  211 database.setTransactionSuccessful();
  212 committed = true;
  213 } finally {
  214     database.endTransaction();
  215     if (!committed) reloadCaches();
  ```
- **Исправление:** считать транзакцию завершённой только после успешного `endTransaction()` либо перечитывать кэши при исключении из фиксации.

### A3-2

- **Severity:** medium
- **Confidence:** probable (по чтению кода)
- **Место:** `Native~/android/analytics/src/main/java/com/daliys/analytics/AnalyticsQueue.java:150–164`
- **Проблема:** `resetIdentity()` присваивает новое значение полю `identity` внутри транзакции. При ошибке фиксации метод не вызывает восстановление `identity` из БД; последующий `getState()` может вернуть новый ID, хотя транзакция откатилась и метаданные в БД остались прежними.
- **Сценарий:** ошибка commit при сбросе идентификатора → вызывающий код повторно обращается к очереди → `getState()` возвращает несохранённый ID, а `getSequenceState()` читает старые метаданные.
- **Цитата:**
  ```java
  150 public synchronized QueueResult resetIdentity() {
  151     database.beginTransaction();
  152     try {
  153         long next = ...
  156         database.delete("metadata", null, null);
  157         identity = newIdentity(next);
  ...
  159         database.setTransactionSuccessful();
  160     } finally {
  161         database.endTransaction();
  162     }
  163     reloadCaches();
  164     return getState();
  ```
- **Исправление:** присваивать `identity` после успешной фиксации или перечитывать его при сбое транзакции.

### Проверено без замечаний

- `readOldest()` пишет заголовок, sequence и длину в big-endian, как ожидает `QueueBatch`; при нехватке буфера расширяет массив.
- UUID-байты в Android форматируются в том же каноническом порядке, который задаёт `EventRecordFormat.WriteUuid`.
- Дубликат `event_id` не увеличивает sequence и счётчики: `INSERT OR IGNORE` возвращает отсутствие вставленной строки, а sequence увеличивается только при успешной вставке.
- В обычных успешных путях удаления `deleteThroughSequence`, `deleteAcknowledged`, истечения срока и eviction счётчики обновляются; `clearAllPendingEvents()` сбрасывает их.
- Тесты, сборки и эмуляторы не запускались. Риск по A3-1 зависит от возможности ошибки SQLite при фиксации транзакции; код не восстанавливает кэши в этом случае.
