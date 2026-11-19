# Протокол и граница реализации

`06-experiments/transport7.py` — исполняемый Python reference M7.
`native/Columns.cs` — C# typed-column packer, отдельный reusable zstd context;
`native/Frame.cs` — полный C# sender packet с header/CRC, пока host-only проверка;
`go/frame.go` — полный decoder по catalog/aliases и external auth context, пока offline API;
`go/main.go` — независимый decoder колонок и dictionary decompression. Это
исследовательская реализация; C#/Go не выданы за законченные SDK/server transport.
Существующий AnalyticsUploader продолжает использовать V1 JSON/gzip Fastest.

Каталог содержит project_id, enum имён 1..255, ключи, canonical shapes и маски
присутствия. ID8 = SHA256 canonical descriptor, первые 8 байт. Внутри известной
пачки используются ID shapes, из которых выводятся event enum/маска/типы; отдельная
маска на каждое событие не дублируется. Имена/ключи остаются в setup descriptor.
Shape reference нормализует порядок полей по ключу: перестановка JSON свойств
не создаёт новую схему. Это проверено на 29 оригинальных queued events из
эмулятора: их порядок отличается от DB jsonb. Сохраняются значения и типы,
но не незначимый порядок JSON ключей. Build-time manifest использует тот же
порядок. Неизвестные формы вызывают ошибку и полный V1 fallback, не отбрасываются.

Универсальный transport не знает имён игровых свойств, правил вычисления SHA
или пар идентификаторов. Он использует только neutral V6 integer/value helpers
и context aliases; `v6.shape`, hash_prediction и property-reference paths не
вызываются. `game_cleanup.py` существует отдельно, только для Puzzle. В Runtime/
не добавлено никаких специфичных для игры строк. Проверены разные project IDs;
схема и authorized_project должны совпасть независимо от совпадения полей.

Кадр:

| Поле | Кодирование |
|---|---|
| magic | ASCII M7 |
| flags |1B, preserve_original_event_uuid=1, integer_model=2, string_model=4, metadata_model=16; остальные запрещены |
| compression |1B, raw=0/zstd1=1 |
| catalog_id |8B, включает project binding |
| alias_epoch |8B |
| dictionary_sha256_prefix |8B, нули для no-dict |
| events | canonical ULEB128,1..500 |
| raw bytes | canonical ULEB128,1..2MiB |
| body | raw или полный standard zstd frame |
| CRC32 |4B, header+body |

Фиксированный заголовок+CRC32 =32 Б плюс 2 varint. Максимальный frame256KiB.
Dictionary ID проверяется даже при raw fallback; mismatch, иной project/origin,
неизвестный epoch/schema, noncanonical varints, окно/размер zstd, trailing bytes
и неподдерживаемые flags отвергаются. CRC не заменяет TLS/authentication.
Регистрация aliases ограничена 65536 slots, атомарно проверяется и содержит epoch;
каждый frame привязан к нему. Повторы frame внутри того же epoch декодируются
без адаптивного entropy state. Authenticated epoch allocation и durable handshake
в service не реализованы. В экспериментах нулевой epoch фиксирован для snapshot;
production должен выделять уникальный namespace и ждать registration ACK.

Raw body использует 5 integer columns: sequence, timestamp, session-elapsed
residual, shape_id, context_slot. По session residual = elapsed_delta - time_delta;
предикторы сбрасываются в каждой пачке. Далее optional n*16 исходных event UUID
и property columns в порядке первого появления (key,type). V6 integer packer
выбирает самый короткий из direct/delta ZigZag-varint/min+bitpack. UInt64 не
приводится к signed. Bool =bit, null =0 payload, UUID/hex =binary dictionary+indices,
string =UTF-8 dictionary+indices, Decimal =точный lexeme, IEEE float сохраняется
точно, включая -0. Python допускает V6 exact fixedpoint; C# пока пишет raw IEEE.
V1 JSON/DB не позволяют узнать исходный CLR float против double: reference
выводит float32/64 tag по точной представимости значения. Production typed ingress
должен передавать исходный tag; DB benchmark не доказывает восстановление CLR типа.
C# boundary использует заранее созданные typed cells/строки/UUID bytes: parsing,
boxing, schema lookup, UTF-8 ingress и подготовка буферов в нулевой GC замер
не входят. Native columns полагаются на предварительно проверенный input.

Alias tuples — immutable origin_install/session и контекст устройства. Сервер
проверяет origin из authenticated request, а project — из своей зарегистрированной
схемы. Никакие чужие aliases не должны приниматься только по клиентскому epoch.
Каталоги/dictionaries надо хранить неизменно, пока в offline очередях остаются
пакеты старых версий. Неподдерживаемая schema, oversized raw/frame или сбой native
codec должны возвращать исходные queued events в V1/split без ACK/deletion.

Не реализованы в production: SDK selection/handshake/fallback, queue→typed arena,
C# typed ingress/catalog resolver/decoder, Go HTTP receiver/persistence/ACK, durable aliases, schema deployment,
atomic persist+dedup+ACK, origin_install migration и production native zstd packaging.
Отдельный research APK уже проверен на Android ARM64 IL2CPP 4KB/16KB; iOS и
production mobile builds не проверены. Прототип проверяет формат/гипотезу размера; эти этапы
нельзя подменить успешным roundtrip в лаборатории.


## Дополнительная integer model (flag2)

Исходный формат остаётся default. При flag2 каждая signed-integer property column
получает один opcode:0=V6 integers,1=residual к timestamp,2=к sequence,
3=к session_elapsed_ms,4=локальная таблица distinct integers+indices.
Выбирается наименьший полностью оплаченный raw payload; ties по меньшему opcode.
Другие типы и пять metadata columns сохраняют исходный формат. Переполнение
при вычитании исключает кандидат; decoder проверяет восстановленную int64 область.
Это key-agnostic правило и не содержит игровых имён. SHA/CSV и identity cleanup
не входят в модель. C# использует заранее выделенные массивы и dictionaries;
все пять opcodes покрыты C#/Python/Go parity и allocation benchmark.

Словари для этого представления обучаются отдельно на тех же train installs.
Новые результаты находятся в05-integer-model-evaluation.md; baseline matrix
не перезаписана. Сервер без capability flag2 должен отвергнуть этот вариант,
а клиент сохранить очередь и повторить исходный режим/V1. Полного production
capability handshake и SDK-интеграции framing по-прежнему нет. Сам C# sender
framing/CRC теперь проверен на всём real holdout (.NET), см.09-full-packet-validation.md.
Полный Go decode независимо проверен на C# packets, см.10-go-packet-validation.md;
это не production middleware/HTTP/database integration.

## Дополнительные модели строк и метаданных

Flag4 добавляет общий exact string codec, flag16 — альтернативный packer пяти
metadata streams. Descriptor с `logical_strings=true` задаёт string type без
зависимости от содержимого (UUID/hex кодируются внутри колонки). Default descriptor
и default кадры сохраняются. String flag4 реализован в Python/C#/Go и проверен
Unity Mono/Android IL2CPP (16 fixtures на каждой платформе, calibrated0 GC).
Metadata flag16 остаётся Python-only; C#/Go не должны принимать его.
Production capability/framing handshake пока не реализован. Метаданные оказались
хуже numeric baseline и в основной кандидат не включены. Формат, отдельные
результаты и пределы доказательства описаны в07-string-table-evaluation.md.
