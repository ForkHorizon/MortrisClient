# CPU, GC, память и проверка Android

Числа в `results/native-csharp.json` и `results/native-real-*.json` — измерения
.NET10.0.5/macOS arm64. Каждая fixture прогревается 100 раз, затем выполняет 1000
pack+native zstd1 операций с заранее созданными input cells, raw/frame buffers,
CCtx и CDict. GC.GetAllocatedBytesForCurrentThread до/после цикла проверяется
assert:0. Таймер и сериализация отчёта находятся вне allocation interval.

Проверены synthetic100, typed edges3, max500 и 3 варианта настоящей пачки 100.
Python читает результат C#; Go независимо распаковывает zstd и проверяет все
колонки. Edge fixture содержит int64 min/max с delta overflow, uint64 max,
-0.0, нецелые IEEE числа, Unicode, null/bool, hex/UUID и Decimal lexeme1.2300.
Ошибка пойманных overflow exceptions из первой версии дала 464000 Б на 1000
итераций; после проверки переполнения без exceptions стало 0. Результаты финального
запуска следует брать из JSON; время меняется с нагрузкой компьютера.

Объём managed input/рабочих массивов не нулевой: они создаются заранее.
Raw buffer2MiB, compressed buffer256KiB, arrays500 cells/values,16k catalog columns,
65536 session predictor slots, dictionary/string-index buffers и строки input.
Native zstd CDict/CCtx также расходуют память; dictionary16–32KiB не равен общему
расходу RAM. Native malloc/realloc/high-water здесь не инструментированы.
C# String dictionary capacity500 заранее создана и переиспользуется. На ошибочных
input/capacity/unsupported primitive возможны exceptions и GC; обещание относится
к проверенному hot path, не ко всем API calls. Ingress validation обязателен.

Integer/value work линейный в числе значений при фиксированном каталоге. C#
делает повторные bounded scans по колонкам/полям, поэтому нельзя выдавать время
для маленькой схемы за гарантию для 16000 columns. Максимум 500 rows и fixed
capacities проверены; dynamic schema rebuild и allocation-free schema miss не
реализованы. Python reference делает управляемые allocations и не Zero-GC.

Исходник `Columns.cs` компилируется как netstandard2.1 library и как .NET10
benchmark. Это подтверждает API-профиль, а не Unity compilation/Burst/IL2CPP
codegen или поведение GC внутри Unity. C# выполняет typed-column stage+zstd,
без полного framing/CRC, queue parsing/JNI, ingress schema mapping, HTTP и retry.
Python full-frame encode/decode измерен отдельно (p50/p95 в benchmark JSON).

## Проверенный Android стенд

Изначально adb devices был пуст. После предложения пользователя запущены
существующие AVD Pixel_8 и Mortris_API_35. На последнем подтверждены Android15,
arm64-v8a, Puzzle1.1.14/debuggable. Его idle queue содержит 29 событий, SQLite/WAL
склонированы и разобраны. Никаких действий в игре/отправки тестового трафика в
production не выполнялось.

В установленной игре работает V1, V7 туда не встроен. В продолжении исследования
создан отдельный APK `com.daliys.transport7.research` с тем же C# packer и native
zstd1.5.7. Игра/SDK не изменялись. Android модуль, SDK/NDK/JDK уже были установлены
в version-root/PlaybackEngines/AndroidPlayer; прежняя проверка только app Contents
ошибочно посчитала их отсутствующими. Unity API подтвердил Android support;
установка/исправление Editor не потребовались.

Теперь проверены Unity Editor Mono и Android15 ARM64 Development IL2CPP на AVD.
Каждый исполнил12 fixtures по1000 pack+zstd, включая реальные100-event пачки,
и выдал raw buffers, побайтно совпадающие с .NET/Python/Go. Проверка0 GC использует
Unity ProfilerRecorder Internal/GC.Alloc с положительным и пустым контролем.
GC.GetAllocatedBytesForCurrentThread в этой Unity возвращает0 даже на явной
аллокации и для доказательства не используется. Полные данные:
[Unity runtime validation](06-unity-runtime-validation.md).

Эмулятор не подтверждает CPU/радио/энергию/температуру физического телефона.
Синхронный1000-iteration benchmark также не является FPS тестом игрового цикла.

До приёмки мобильных критериев нужен отдельный player с тем же preallocated
packer и dictionary, release IL2CPP, без отправки в production: warmup отдельно,
100 events, p50/p95/p99 всего encode и Track→persist→send; GC.Alloc recorder и
native allocation counters; cold-start, schema miss, maximum payload, retries.
Затем физический Android/iPhone среднего класса для thermal/FPS и энергии при
фиксированных cadence/brightness/radio и повторяемых A/B блоках.

Сейчас подтверждено0 GC.Alloc в проверенном typed-column+zstd этапе .NET,
Unity Editor и Android IL2CPP на эмуляторе. Полный SDK ingress/framing/JNI/HTTP,
физический телефон и thermal/FPS/energy gates не подтверждены. Цели размера
V7 также ещё не достигнуты.
