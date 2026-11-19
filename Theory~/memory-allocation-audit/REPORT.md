# Отчёт: managed allocations и временная память в analytics SDK

Дата: 2026-10-25  
Срез исходников: 35c564d  
Метод: статический аудит исходников семью отдельными агентами с последующей сверкой путей в коде и Graphify.  
Изменения: создан только этот отчёт. Исходники не менялись; тесты, сборки и профилировщик не запускались.

## Краткий вывод

Есть два разных класса затрат:

1. **Мусор Unity/C# при записи события.** На каждый обычный Track() бинарный writer повторно использует свой буфер, но код всё ещё создаёт два временных byte[16] при записи GUID. Свойства типа float и decimal дополнительно создают промежуточную строку. Эти места просты для оптимизации, но фактический вклад в GC ещё не измерен.
2. **Крупные временные копии при пакетной записи и отправке.** Буфер событий копируется в новый массив перед JNI, JNI копирует его в Java, а Java делает отдельную копию каждого record для SQLite. При V7-отправке появляются ещё массивы компрессии и frame. Это происходит реже, чем Track(), но может создавать большие пики managed/Java heap и крупные сборки мусора.

Отдельно есть удержание памяти: растущие рабочие буферы остаются на пиковом размере, а таблица контекстных алиасов V7 может накапливаться до лимита. Удерживаемая память не равна GC churn, поэтому её следует измерять отдельно.

**Самый дешёвый следующий шаг для кода:** убрать временные GUID-массивы и строки float/decimal.  
**Самый перспективный следующий шаг для пакетного пути:** после измерения сократить копии Drain → JNI → Java/SQLite и V7 compress → frame.

## Подтверждённые места выделения

Уровень уверенности показывает наличие выделения по коду, а не его измеренную долю в кадре.

| Приоритет | Путь | Что выделяется | Частота и значение | Минимальный вариант |
|---|---|---|---|---|
| Высокий по частоте, небольшой объём | Track() → EventRecordWriter.Begin | EventRecordFormat.WriteUuid дважды вызывает Guid.ToByteArray(): два временных массива на 16 байт на событие ([EventRecord.cs:49-57](../../Runtime/Internal/Transport/EventRecord.cs), вызовы из [AnalyticsRuntime.cs:79-95](../../Runtime/Internal/AnalyticsRuntime.cs)). | Подтверждено для каждого записываемого события. Суммарно минимум 32 байта массива на событие плюс заголовки объектов; размер заголовков зависит от Unity runtime. | Записывать поля GUID прямо в целевой буфер, сохранив канонический порядок байтов. Небольшое локальное изменение. |
| Зависит от типов свойств | Track() → numeric encoding | float форматируется в строку "R", затем эта строка снова разбирается; decimal также сначала превращается в строку ([EventRecord.cs:192-230](../../Runtime/Internal/Transport/EventRecord.cs)). | Одна или более промежуточных строк на каждое такое свойство. Для int, long, double и обычных строк этот конкретный промежуточный путь не используется. | Классифицировать число и писать значение напрямую в record, сохранив текущие правила совместимости V1/V7. Приоритизировать по реальной доле float/decimal. |
| Каждый непустой flush | EventBuffer.Drain → JNI enqueue | Drain создаёт массив размером всего кадра и копирует накопленные данные ([EventBuffer.cs:39-50](../../Runtime/Internal/Transport/EventBuffer.cs)); Android bridge затем создаёт Java byte[] через AndroidJNI.ToByteArray ([AndroidQueueBridge.cs:98-111](../../Runtime/Internal/AndroidQueueBridge.cs)). | Две копии размера пакета на границе C# → Java. Настроенный предел handoff — 1 MiB плюс приоритетный запас; реальный размер и частота зависят от трафика. | Измерить сначала. Затем рассмотреть обмен владением двух буферов или повторное использование массивов после синхронного JNI-вызова. Нельзя переиспользовать массив до завершения Java-вызова или при восстановлении после ошибки. |
| Каждый record, записанный в SQLite | Java enqueueRecords | Arrays.copyOfRange создаёт новую Java byte[] для каждого record перед SQLiteStatement.bindBlob ([AnalyticsQueue.java:178-229](../../Native~/android/analytics/src/main/java/com/daliys/analytics/AnalyticsQueue.java)). | Java heap churn пропорционален числу и суммарному размеру записей. Прямой bind среза надо подтвердить для целевой Android API; текущая сигнатура принимает отдельный массив. | Не обходить копирование через небезопасную переиспользуемую память. Сначала проверить API/профиль; изменение интерфейса записи может оказаться больше, чем выигрыш. |
| Каждый вызов readOldest | Java queue read → C# QueueBatch | Java создаёт оценочный массив 4 + rows*256, может несколько раз расширить его, затем всегда обрезает копией до точной длины ([AnalyticsQueue.java:235-257](../../Native~/android/analytics/src/main/java/com/daliys/analytics/AnalyticsQueue.java)); JNI создаёт отдельный managed-массив через FromByteArray ([AndroidQueueBridge.cs:114-120](../../Runtime/Internal/AndroidQueueBridge.cs)). | Несколько временных массивов на чтение; при крупных payload могут быть росты и копии. Частота зависит от V1/V7 и размера upload batch. | Если профайлер покажет вклад, предварительно посчитать длину выбранных строк и выделять точный массив один раз. Дополнительный проход по БД надо сопоставить с выигрышем. |
| Каждая V7-строка при кодировании | M7EventEncoder.Encode | На каждое событие создаются M7Event, список свойств, массив M7Cell[] и M7Row; на пакет дополнительно создаются массивы строк и последовательностей, словарь и список ([M7EventEncoder.cs:54-92](../../Runtime/Internal/Transport/M7EventEncoder.cs), [M7Event.cs:57-86](../../Runtime/Internal/Transport/M7Event.cs)). | Подтверждённые managed allocations на upload batch, до 500 строк на один кадр. Это не выделения игрового вызова Track(). | Более крупная оптимизация: формировать строки из повторно используемого ParsedEvent, уменьшая промежуточные объекты/списки/массивы. Требует сохранить сортировку ключей и соответствие каталогу. |
| Каждый V7 пакет | Zstd и сборка frame | Компрессор выделяет compressBound массив, затем точный массив результата ([M7Zstd.cs:47-58](../../Runtime/Internal/Transport/M7Zstd.cs)); frame encoder выделяет временный packet buffer, копирует тело и выделяет ещё один массив точной длины с копией ([M7FrameEncoder.cs:57-74](../../Runtime/Internal/Transport/M7FrameEncoder.cs)). | Подтверждено: несколько крупных массивов сосуществуют во время пакетирования. Наиболее ясный источник пиков памяти в V7 отправке. | Возвращать длину записанного результата в повторно используемом output buffer и собирать итоговый frame за одну копию. Менять после профиля, сохранив raw fallback и время жизни массива до окончания HTTP-запроса. |
| Каждый успешный V7 HTTP ответ | Response parsing | V7Response декодирует тело в строку и разбирает JSON для ошибки; успешные обработчики повторно разбирают ту же строку ([V7Types.cs:13-20](../../Runtime/Internal/Transport/V7Types.cs), [V7Session.cs:202-210,378-383](../../Runtime/Internal/Transport/V7Session.cs)). | Повторное создание JSON object graph на ответ; пакетные ответы повторяются. Тела ответа обычно малы, поэтому ниже по приоритету, чем байтовые массивы. | На 2xx пропустить разбор error-code; либо разобрать ответ один раз и передать поля обработчику. |
| Только V1/fallback batch | JSON + gzip | Создаётся JSON событий, обёртка batch, затем gzip stream/буфер и ToArray() ([AnalyticsUploader.cs:309-330](../../Runtime/Internal/AnalyticsUploader.cs)). | Несколько строк и массивов на запрос; фоновая отправка, не игровой Track() путь. | Оставить до профиля; при заметном вкладе gzip-ить UTF-8 поток напрямую, чтобы не держать несколько полных копий тела. |

## Удержание памяти и редкие случаи

- EventBuffer растёт геометрически с 16 KiB, но Clear() не уменьшает буфер. При лимите около 1 MiB плюс запасе один крупный burst может оставить примерно 2 MiB backing array на жизнь worker ([EventBuffer.cs:12,68-79](../../Runtime/Internal/Transport/EventBuffer.cs), лимиты в [AnalyticsPersistenceWorker.cs:30](../../Runtime/Internal/AnalyticsPersistenceWorker.cs)). Это удержание, а не постоянные аллокации.
- При ошибке записи EventBuffer.Restore каждый раз создаёт объединённый массив, даже если существующая ёмкость достаточна ([EventBuffer.cs:53-65](../../Runtime/Internal/Transport/EventBuffer.cs), вызывается из [AnalyticsPersistenceWorker.cs:218-231](../../Runtime/Internal/AnalyticsPersistenceWorker.cs)). Большой churn только при повторных ошибках persistence.
- M7FrameEncoder._raw переиспользуется и может удерживать до 2 MiB после расширения ([M7FrameEncoder.cs:13-22,45-55](../../Runtime/Internal/Transport/M7FrameEncoder.cs)). Это намеренный обмен удержанной памятью на меньшее число повторных выделений.
- M7Aliases удерживает записи контекста и ограничивает таблицу величиной 65 536 ([M7Aliases.cs:14-16,30-40](../../Runtime/Internal/Transport/M7Aliases.cs)). При обычном стабильном app/device context таблица не должна расти по каждой сессии; частая смена контекста может накапливать строки до лимита.
- CompleteFlushes создаёт snapshot List и объект FlushResult даже без ожидающих FlushAsync ([AnalyticsPersistenceWorker.cs:268-279](../../Runtime/Internal/AnalyticsPersistenceWorker.cs)). Это мелкая аллокация на завершение worker pass; можно пропустить создание результата при нуле ожиданий.
- Отменённые FlushAsync остаются в списке ожиданий до следующего завершения worker pass ([AnalyticsPersistenceWorker.cs:107-120,268-279](../../Runtime/Internal/AnalyticsPersistenceWorker.cs)). Это временное удержание при долгой сети/очереди; в обычном режиме не выглядит постоянной утечкой.
- Schedule создаёт callback для ThreadPool.QueueUserWorkItem на фактический проход worker ([AnalyticsPersistenceWorker.cs:137-144](../../Runtime/Internal/AnalyticsPersistenceWorker.cs)). Это одна небольшая аллокация на pass, объединённая _isScheduled; не одна на событие.

## Что уже сделано хорошо

- EventRecordWriter хранит thread-local буфер и расширяет его только если размер записи превысил прежнюю ёмкость ([EventRecord.cs:128-135,239-253](../../Runtime/Internal/Transport/EventRecord.cs)).
- Проверка обычного Dictionary<string, object> использует struct enumerator, числовая оценка размера использует stackalloc + TryFormat, а не строку ([EventValidator.cs:30-51,145-172](../../Runtime/Internal/EventValidator.cs)). Для других реализаций IReadOnlyDictionary enumerator может быть упакован/создан объектом — зависит от реализации.
- EventBuffer обычно добавляет записи в заранее выделенный массив без отдельного массива на каждый event ([EventBuffer.cs:12,24-35](../../Runtime/Internal/Transport/EventBuffer.cs)).
- M7Columns повторно использует рабочие массивы и словари между пакетами ([M7Columns.cs:21-39](../../Runtime/Internal/Transport/M7Columns.cs)).
- Android bridge уже кэширует method IDs для низкоуровневых JNI вызовов и повторно использует jvalue[]; он избегает тяжёлого reflection path на enqueue/read. Сам payload всё ещё копируется через стандартные byte[] JNI API ([AndroidQueueBridge.cs:43-64,98-120](../../Runtime/Internal/AndroidQueueBridge.cs)).

## Рекомендуемый порядок действий

1. **Измерить до переписывания пакетных буферов.** На Android player захватить Unity Profiler GC.Alloc с call stacks для тёплого Track() и upload/persist pass; отдельно включить Java heap allocation recording для enqueue/read. Сравнивать обычные события, строковые свойства, float/decimal, burst и V7/V1 fallback.
2. **Сделать маленькие изменения в hot path:** прямой GUID encoding; прямое число encoding для float/decimal. Проверить точную сериализацию всех поддерживаемых граничных значений.
3. **Если batch массивы окажутся основным вкладом:** уменьшить промежуточные копии в Drain/JNI/Java с явным владением буфером до возврата синхронного JNI вызова. Сохранить восстановление batch при ошибке.
4. **Если V7 packet peak окажется заметным:** объединить сборку frame и повторно использовать компрессионный output; затем отдельно оценить промежуточные M7Event/List/M7Cell[] allocations.
5. **Только после этих замеров** трогать V1 gzip/JSON, кэш строковых значений, алиасы и редкие waiter/control allocations.

Для измерений не полагаться на GC.GetAllocatedBytesForCurrentThread() в Unity: в проектной памяти зафиксирован случай Unity Editor Mono, где вызов возвращал ноль и для искусственно созданной аллокации. Использовать проверенный Unity Profiler GC.Alloc маркер и устройство; отдельно смотреть Java heap. Статический аудит не заменяет эти замеры.

## Покрытие агентов

Семь read-only проходов охватили: Track()/валидацию; binary record и сериализацию; worker/buffer/timers; Android SQLite queue; V7 encoding; JNI/zstd/HTTP; session и uploader. Все агенты подтвердили отсутствие изменений кода и запуска тестов/сборок.

## Ограничения и риск

Это аудит аллокаций по коду, а не доказательство того, какая функция создаёт наблюдаемые GC spikes в реальной игре. Не измерялись байты на событие, сборки GC, кадры, Java heap/RSS или частота fallback. Приоритет оптимизаций выше — инженерная оценка по частоте/размеру массивов; подтверждать её надо профилем конкретного Android устройства и Unity runtime.
