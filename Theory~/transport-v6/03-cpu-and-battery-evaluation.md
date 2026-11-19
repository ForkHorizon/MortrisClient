# CPU, память, GC и батарея

Доказательства ограничены средой macOS arm64. Измерения ниже не CPU-такты телефона. Время в микросекундах зависит от частоты/нагрузки/FFI; пересчитывать его в mobile cycles нельзя. Python allocation peaks не показывают C#/IL2CPP GC. Нативный compressor stage не является полным ingestion/encode/native SDK.

## Что измерено

C `mtb6_ints` читает caller-owned int64 array, вычисляет стоимость четырёх простых layouts и один раз пишет выбранный. Сложность O(n); до четырёх коротких проходов, без дерева context probabilities, SHA и кэша BLAKE2s. n<=500, output capacity проверяется до записи. Отдельного временного массива нет; O(1) рабочие scalar locals, output<=1+10*n. Используется clang `__int128` для проверки разности без signed overflow; порт в C#/Burst обязан заменить это проверкой переполнения, а не обрезанием.


Сопоставлено 1006 целых колонок, включая крайние int64, ширину64, константы и случайные длины. Проверены маленькие output buffers. `nm -u` не содержит malloc/calloc/realloc/free; kernel не аллоцирует heap. Это свойство **только integer kernel**.

| Корпус | n | Raw B | zstd1 B/µs | zstd19 B/µs | LZ4 B/µs | CCtx1/19 B | Python encode peak B |
|---|---|---|---|---|---|---|---|
| base | 100 | 1746 | 1626/6.034 | 1566/58.636 | 1641/1.000 | 48582/223996 | 292341 |
| rich | 100 | 5576 | 3835/11.818 | 3645/278.783 | 4599/4.003 | 112118/364774 | 349780 |
| alt | 100 | 33536 | 14063/29.115 | 12478/4835.494 | 17410/18.746 | 184152/1642134 | 1044856 |
| drift | 23 | 544 | 424/4.359 | 386/29.699 | 411/0.750 | 35856/197911 | 151387 |


Таблица — выбранная большая пачка каждого профиля, одинаковый заранее подготовленный V6 raw buffer. CCtx переиспользуется; создание/FFI/Python preprocessing/canonical rendering вне compressor-stage сравнения. zstd19 здесь БЕЗ V4 dictionary, это не V4 benchmark. Python encode peak включает reference traversal/packing/compression/source rendering, но не startup registry; native allocator compression contexts tracemalloc не видит. LZ4 block bytes без V6 header; полная матрица LZ4 есть в 02. Ни memory peak, ни маленький compressor-stage не объявляются полной памятью транспорта.


| Корпус | V6 Python encode ms/100 events | V5 Python encode ms/100 events | V6 decode ms/100 events | V5 decode ms/100 events |
|---|---|---|---|---|
| base | 3.576 | 25.848 | 4.707 | 29.245 |
| rich | 5.944 | 59.590 | 7.463 | 65.581 |
| alt | 2.369 | 91.274 | 3.073 | 123.933 |
| drift | 2.751 | 25.485 | 3.676 | 28.977 |


Это медиана одних и тех же первых трёх пачек holdout в Python reference. Небольшая выборка, validation/model management реализаций различается; это ориентир сложности, не прогноз ускорения нативного V5. В V6 остались dictionary lookups, string dedup, shape compilation escapes, JSON rendering и Python allocations. В replay SHA выполняется на клиенте. Поэтому «асимметричный zero-overhead engine» пока гипотеза реализации, а не достигнутый production результат.

## Архитектура Unity и цена памяти

Предлагаемый production путь: build compiler генерирует event/field IDs, static masks и typed writers. Горячий writer принимает struct/scalars/уже подготовленные UTF-8 spans; данные пишутся в заранее выделенный bounded NativeArray/arena. Не использовать Dictionary<string,object>, boxing, LINQ, новую строку для UUID/hex или JSON на игровом потоке. Существующий SDK в этом исследовании не заменялся — его allocations не исчезли.

Пример верхнего проектного бюджета cap100/max32 properties: 100 EventRecord по40B =4000B; 3200 ValueCell по16B =51200B; строковая arena с envelope properties budget8192B/event =819200B. Затем отдельные raw scratch<=2MiB и frame buffer<=256KiB плюс CCtx, alias cache, descriptor, queue/JNI/HTTP и временные копии. Это консервативный дизайн, не измеренный Unity размер struct. До 2MiB/256KiB буферы выделять один раз в native heap, не stackalloc; ABI alignment сверять sizeof на устройстве. Если выбрать меньшие arenas, вводить явную fallback/split без потери событий. SDK metadata strings могут быть длиннее property budget — их нужно учитывать отдельно, нельзя объявлять8192 универсальным размером события.

NativeArray.Allocator.Persistent выделяется при init и освобождается при shutdown. Native allocation ≠ GC allocation: `0 GC Alloc` не означает ноль RAM или отсутствие malloc. Контекст компрессора, dictionary если появится, alias map и retry buffers также требуют бюджета; warm reuse не доказывает отсутствие realloc при росте пачки. В этом исследовании число malloc zstd не трассировалось. Самый строгий вариант — заранее оценённый static workspace или allocation instrumentation на максимальных размерах.

Burst поддерживает unmanaged structs и native containers; string/decimal managed values нельзя просто перенести в job. UTF-8 encode, registry miss и Decimal escape должны иметь отдельный ограниченный путь вне hot loop. Это следует из [официального ограничения типов Burst](https://docs.unity3d.com/Packages/com.unity.burst@1.8/manual/csharp-type-support.html). Span поддержка зависит от editor/runtime; portable native C buffer ABI проще проверять отдельно. C kernel уже есть, полного native/Burst property codec, C# façade и Go decoder пока нет.

zstd требует учитывать весь CCtx и возможный рост workspace, а не только словарь; рекомендации по reuse и памяти: [zstd memory guide](https://github.com/facebook/zstd/wiki/Using-libzstd-in-a-memory-constrained-environment), [pinned zstd1.5.7 API](https://github.com/facebook/zstd/blob/v1.5.7/lib/zstd.h). У LZ4 safe decoder размер destination ограничен frame header: [pinned LZ4 1.10 API](https://github.com/lz4/lz4/blob/v1.10.0/lib/lz4.h). В текущей Python обвязке обоих компрессоров allocations есть.

## Батарея и план проверки на устройстве

Фактически проверено `adb devices -l`: подключённых устройств нет. Поэтому энергия, температура, мобильные CPU cycles, IL2CPP/Burst codegen и managed GC не измерялись. Нет численного заявления о процентах батареи.

Перед включением: одинаковый persisted trace, hardware/OS/build, фиксированные batch cadence и frame budget; release IL2CPP на среднем Android/iPhone; warm-up отдельно от steady-state. Измерить весь Track→arena→encode→enqueue/send с p50/p95/p99 CPU time, GC.Alloc recorder, native high-water/allocation counters, bytes including retry/registration. Отдельно проверить foreground frame drops и thermal throttling. После этого чередовать достаточно длинные A/B блоки V5/V6 при фиксированных radio/brightness/temperature и измерять энергию внешним power monitor либо calibrated platform tooling, повторять с доверительными интервалами. CPU-stage быстрее может проиграть по энергии из-за большего radio payload/частоты запросов; серверная CPU тоже не безгранична в смысле стоимости эксплуатации.

Тесты Zero-GC должны охватить uint64/signed zero, schema miss, длинные строки, максимальную пачку, reconnect и retries. Нельзя объявить zero-GC, измерив только повтор одного удачного маленького encode.
