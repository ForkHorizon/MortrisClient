## Выводы

### A2-1

- **Severity:** medium
- **Confidence:** confirmed by code reading
- **Location:** `Runtime/Internal/Transport/EventRecord.cs:208, 229, 665`
- **What's wrong:** дробная часть `decimal` преобразуется в `double`, а затем JSON снова форматирует уже округлённое значение. Старый V1 сериализатор сохранял исходное десятичное представление.
- **Scenario:** приложение отслеживает `0.12345678901234567890m` → значение записывается как `double` → V1 отправляет примерно `0.12345678901234568`.
- **Code quote:**
  ```csharp
  208  AddRawDouble(key, double.Parse(lexeme, NumberStyles.Float, CultureInfo.InvariantCulture));
  ...
  229  case decimal m: AddLexeme(key, m.ToString(CultureInfo.InvariantCulture)); break;
  ...
  665  case EventRecordFormat.TagDouble: json.Append(p.D.ToString("R", CultureInfo.InvariantCulture)); break;
  ```
- **Short fix idea:** хранить дробные `decimal` отдельно либо сохранять точный JSON-лексемный текст для V1. Это затрагивает принятый `EventValidator` тип `decimal`.

### A2-2

- **Severity:** low
- **Confidence:** confirmed by code reading
- **Location:** `Runtime/Internal/Transport/EventRecord.cs:35–42`
- **What's wrong:** декодер принимает десятибайтовый `ulong` varint, у которого десятый байт содержит биты помимо младшего. Такое переполнение при сдвиге по C# может превратиться в неверное значение вместо ошибки формата.
- **Scenario:** повреждённая строка varint в сохранённой записи содержит девять байтов `0x80`, затем `0x02` → декодер принимает её как ноль → поле события меняется без ошибки.
- **Code quote:**
  ```csharp
  35  for (var shift = 0; shift < 70; shift += 7)
  36  {
  37      if (position >= end) throw new FormatException("Event record is truncated.");
  38      var b = buffer[position++];
  39      result |= (ulong)(b & 127) << shift;
  40      if (b < 128) return result;
  41  }
  42  throw new FormatException("Event record has an invalid varint.");
  ```
- **Short fix idea:** на последнем байте принимать только значения `0` или `1`.

### A2-3

- **Severity:** low
- **Confidence:** confirmed by code reading
- **Location:** `Runtime/Internal/Transport/EventRecord.cs:292–341`; `Runtime/Internal/AnalyticsUploader.cs:204–213, 271–273`
- **What's wrong:** повреждённая запись вызывает `FormatException` при чтении. V7 возвращает fallback, затем V1 читает ту же запись и исключение приводит к backoff; запись остаётся первой в очереди и может блокировать следующие события при каждом повторе.
- **Scenario:** повреждённая запись оказывается в durable queue → V7 не кодирует batch → V1 падает на `ToJsonArray` → uploader откладывает попытку → повреждённая запись остаётся в очереди перед корректными.
- **Code quote:**
  ```csharp
  204  var events = queue.ReadOldest(batchSize);
  ...
  213  var raw = events.ToJsonArray(_reader);
  ...
  271  catch (Exception)
  272  {
  273      return BackOff(now, null);
  ```
- **Short fix idea:** определить политику для заведомо нечитаемой записи, чтобы она не блокировала очередь. Риск относится к повреждённым локальным данным; нормальный путь записи создаёт структурно корректные записи.

## Checked

- `EventBuffer.Restore` добавляет отклонённый frame перед событиями, пришедшими позже; порядок при обычных размерах сохраняется.
- UUID записывается и читается в canonical byte order; парсер требует dashed-формат UUID.
- Reader проверяет границы основных строковых полей и ограничивает число свойств значением 1024.
- Сравнение `AddDouble` и классификации V7 согласовано для целых `double`; `EventValidator` отклоняет NaN и Infinity до записи.
- Старый JSON payload конвертируется в record; `FromJson` проверяет UUID, timestamp, timezone, свойства и целочисленные поля.

Не запускал тесты, сборки или Unity согласно ограничениям аудита. Других подтверждённых дефектов в проверенных участках не установил.
