# Архитектура MTB6 research v1

Статус: полностью декодируемый Python reference + бинарный компилятор схем и независимый C integer kernel. Не SDK, не сервер production, не полный C#/Go порт. Кодек намеренно меньше V5: без адаптивной арифметической модели и cross-batch probability state. Однако alias registry остаётся обязательным состоянием.

## Контракт без потерь

Два явно разных контракта: historical (V1 minus event_id, как V4/V5) и full V1 (preserve_ids=True, исходный UUID каждого события включён). Никакой детерминированный UUID из sequence не равен случайному UUID исходного события. Full mode оплачивает 16 байт/событие до компрессии. Уникальные случайные UUID почти не сжимаются.

Сервер восстанавливает canonical source byte-for-byte, включая порядок свойств, session/device context, sequence, время и значения. Python типы primitive/Decimal и signed zero проверяются отдельно. Float32/64 tag inferred из representability; исходная CLR-разница float vs double не выводится из JSON, для production writer должен передавать исходный type tag. Canonical baseline фиксирует project_id и SDK name/version и sent_at=last_ts+250ms. Иной source/envelope/sent_at кодируется literal escape с точными байтами. Нет округления float ради размера.

Прототип принимает уже типизированные batch dicts; это исследовательский слой над persisted source. При новой неподдерживаемой primitive/schema/большом frame клиент должен сохранить очередь и использовать исходный V1/разделить пачку. Автоматическая SDK fallback-интеграция не реализована. Сервер проверяет source limits аудированным V5 source_info, а не принимает произвольные значения после распаковки.

## Статическая схема и build/store compile

`Schema.train` — stand-in для build-time event manifest: читает только train202 и фиксирует отсортированные формы `(event_name, ordered [(key,type)])`. В production manifest должен перечислять реальные варианты build_number/app_version, сервер должен хранить их неизменно по schema ID; build GUID сам по себе не доказывает схему.

`schema_tools.py` генерирует `results/schema-*.bin`: magic MS6, schema ID8 (SHA256 canonical JSON descriptor, первые8 байт), count имён/count ключей, length-prefixed UTF-8 имена/ключи, count shapes, для каждой формы event enum varint, presence mask фиксированной длины ceil(keys/8), ordered field count и пары key ID/type byte. `unpack_schema` восстанавливает descriptor, сверяет ID и маску. Это компактная бинарная store-table; JSON остаётся удобным audit input. В таблице есть строки, на известных событиях на проводе их нет.

Shape ID совмещает event enum, набор присутствующих полей, их типы и порядок. Base имеет 12 форм и помещается в uint8; alt имеет больше форм и требует ushort/varint. Пятибитный ID нельзя навязать всем корпусам. Frame колонка shape IDs сжимается integer packer; количество полей ограничено32. Явная маска на событие реализована как контрольная абляция, а не скрыта как бесплатная оптимизация.

Неизвестные формы описываются inline length-prefixed JSON массивом дополнительных shapes, только на эту пачку; сервер валидирует длины, типы, дубликаты и алиасы. Это сохраняет данные при drift, не меняет зарегистрированную схему и не скрывает setup. Нет silent dropping неизвестных полей. Negotiation передаёт тот же immutable descriptor один раз и получает ID8; стоимость реального сериализованного обмена приведена в benchmark.

## Алиасы и handshake

Контекст = `(origin_install_uuid, session_uuid, app_version, build_number, platform, os_version, device_class, locale, tz_minutes)`. Подготовка startup/нового контекста создаёт регистрационный payload: namespace epoch8 и zstd-1 JSON `[first_slot, records]`. Ответ: epoch8+varint(next_slot). Slot — индекс0..65535 в этом namespace. Все регистрации/ответы оплачены; «всегда1–2байта» неверно для больших таблиц. В корпусах player_id/device_id как отдельных полей нет; не придуманы искусственные выигрыши от их удаления.

Сервер выделяет/подтверждает namespace в аутентифицированном channel. Локальный стенд моделирует согласованную таблицу в двух экземплярах и передаёт сериализованный payload через accept. Это не реализация credential negotiation, конкурирующего распределения slots или durable DB. Client register подготавливает записи; production должен использовать их только после ACK. В измеренном сценарии accept всегда предшествует encode.

Каждый data frame содержит epoch8: после restart нельзя переиспользовать slot под другое значение незаметно. Регистрация атомарно проверяется перед вставкой. Сервер принимает frame только для authorized_origin, из вызывающего authenticated контекста; смешивание origin отвергается. CRC не заменяет аутентификацию. Имя пользователя/credential не отправляется в каждом событии, но auth запроса снаружи протокола остаётся.

Missing schema/alias/epoch → fail closed, очередь сохраняется; re-register в новом namespace и повторно encode исходных событий. Не повторять старый frame в новом epoch. Схема/алиасы неизменяемы, entropy state между пачками нет: потерянный ACK не ломает декодирование следующего frame. Приём/ACK данных и дедупликация должны атомарно сохранять canonical events по `(project, origin, sequence)`; partial ACK, конфликты, reset identity и server persistence здесь спроектированы, но не реализованы как service. Хранить origin первоначального события, не заменять его текущим install после reset.

## Бинарный кадр

Все multibyte числа little-endian или canonical ULEB128. Заголовок:

| Поле | Размер |
|---|---|
| magic `M6` | 2 |
| flags: replay=1, full IDs=2, explicit mask=4, literal=8 | 1 |
| compression: raw=0 / standard zstd=1 / raw LZ4 block=2 | 1 |
| schema ID | 8 |
| alias namespace epoch | 8 |
| event count (1..500) | ULEB128 |
| uncompressed raw size (1..2MiB) | ULEB128 |
| body | remaining minus4 |
| CRC32(header+encoded body) | 4 |

Фиксированные затраты24 байта плюс два varint. Максимальный frame256KiB. zstd standard frame включает собственные headers; не используются ни dictionary, ни magicless savings, ни незаявленные assets. LZ4 block использует raw size из заголовка; safe decoder требует точный decoded size. Raw fallback выбирается, если компрессия не уменьшает буфер. CRC проверяется до распаковки. zstd window/content size и регистрация ограничены; лишние/truncated bytes, padding и неизвестные flags отвергаются.

Raw normal body:

1. length-prefixed inline extra shapes (JSON; `[]` если нет).
2. Пять integer columns длиной n: sequence, ts_ms, elapsed residual, shape ID, context slot.
3. При full-ID flag — n*16 исходных event UUID.
4. При explicit mask flag — n масок, размер вычисляется из union property keys зарегистрированных и дополнительных форм; decoder сверяет их с shape.
5. Property columns в порядке первого появления `(field key,type)` при обходе событий и ordered shape fields. Количество элементов выводится из shapes; отдельного count на каждый value нет.

elapsed residual = первый elapsed по session, затем `elapsed - previous_elapsed - ts + previous_ts`. Все предикторы сбрасываются на batch boundary; не нужен state hit. sequence gaps и clock jumps сохраняются.

Integer modes0/1: direct или delta ZigZag ULEB128. Modes2/3: direct/delta min int64, width byte0..64, LSB-first packed unsigned residual. Выбирается самый короткий из четырёх полностью оплаченных кандидатов, стабильный tie order0,2,1,3. Delta overflow → кандидат исключён. Нули/постоянные колонки имеют width0. cell_x/y часто требуют3/4бита; поля вне диапазона не обрезаются. Simple8b/FSE не добавлены: это следующий эксперимент, не требование формата. C-реализация тех же четырёх кандидатов проверяет output capacity до записи.

Bool — один бит. Null — ноль payload. UInt64 — ULEB128 без signed conversion. Float — mode0 exact f32/f64 bytes; mode1 integer/100, только если восстановление исходных IEEE bits каждого значения строго совпадает и кандидат короче. Отрицательный ноль и случайные float автоматически остаются raw. String/UUID/hex/Decimal text — per-column distinct table + integer indices; UUID binary16, hex length+binary bytes, строка length+UTF-8 (surrogatepass внутри reference, escaped JSON на выходе). Decimal lexeme сохраняется. Дубликат app_version, совпавший по типу и сериализации с context, не имеет payload; wave_attempt_id ссылается на предыдущий attempt_id только после точной проверки. Иначе обычный тип/inline shape escape.

Literal flag8 несовместим с остальными flags; body — точный исходный source JSON. На decode тот же semantic limit и origin authorization. Это сохраняет необычный sent_at/envelope/JSON formatting без дорогого diff-патча.

## Хеш: что действительно доказано

Локальный `transport-v2/04-experiments/gen.py` создаёт в начале сессии `sha256(rng.randbytes(8))`, затем при успешной установке `sha256(previous_hex_ascii + bytes(block_id,cell_x,cell_y))`. Это не SHA полного поля. Начальное значение и произвольные расхождения не выводятся из событий. Смена attempt не гарантирует reset цепочки; нельзя это придумывать на сервере.

Baseline хранит уникальные бинарные32B значения в колонке и ссылки на повторы. Replay передаёт один бит на hash occurrence:1 = проверенная предикция,0 = anchor32B. Первый хеш в каждой пачке — anchor. При placement_resolved/outcome=placed сервер делает именно указанную SHA с точными byte coords; иначе предикция — предыдущий хеш. Любое несовпадение сохраняет anchor. Эффект около6Б/событие на base объясняется новыми случайными32B хешами успешных установок, а не плохим сжатием hex-алфавита.

На реальной игре такой режим допустим только после независимого replay actual telemetry и тестов всех resets/undo/rejected/missing actions/version changes. Удалить все хеши или заменить их одним «подтверждающим битом» без anchor нельзя. Client reference вычисляет SHA для проверки предикции; вариант с нулевой новой SHA-работой требует доказанного producer contract/уже вычисленного game state, здесь не реализован. Не-lossless удаление поля в отдельной абляции не выдаётся за replay.
