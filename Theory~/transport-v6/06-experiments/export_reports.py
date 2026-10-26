"""Render measured numbers into the required reports; no hand-entered benchmark data."""
import json,statistics
from pathlib import Path
from support import ROOT, wire
R=ROOT/'results';DOC=ROOT.parent
profiles=('base','rich','alt','drift')
data={p:json.loads((R/f'bench-{p}.json').read_text()) for p in profiles}
native=json.loads((R/'native.json').read_text())
confirm=json.loads((R/'confirmation2601.json').read_text())
compilation=json.loads((R/'schema-compilation.json').read_text())
rawfields=json.loads((R/'field-costs.json').read_text())

def write(name,s):
    (DOC/name).write_text(s.strip()+'\n')

def table(header,rows):
    return '| '+' | '.join(header)+' |\n|'+'|'.join(['---']*len(header))+'|\n'+''.join('| '+' | '.join(str(v) for v in row)+' |\n' for row in rows)

def f(v):return f'{v:.3f}'

fresh={p:data[p]['rows']['holdout1729'] for p in profiles}
main=table(['Корпус','V1 JSON, полный','V1 gzip-1, полный','V4 zstd-19','V5 stateless','V6 zstd-1','V6 replay*','V6 полный V1'],[[p,f(r['V1_full_json_B_event']),f(r['V1_full_gzip1_B_event']),f(r['V4_zstd19_B_event']),f(r['V5_stateless_B_event']),f(r['V6']['zstd1']['body_B_event']),f(r['V6']['replay_zstd1']['body_B_event']),f(r['V6']['strict_V1_ids_zstd1']['body_B_event'])] for p,r in fresh.items()])
base=fresh['base']
write('00-summary.md',f'''
# Transport V6: результат исследования

Прототип реализован, но цель <10–12 Б/событие без игровой предикции и <5–7 Б/событие с ней **не достигнута**. На base/holdout1729: обычный V6 = {f(base['V6']['zstd1']['body_B_event'])}, условный replay = {f(base['V6']['replay_zstd1']['body_B_event'])}, V5 = {f(base['V5_stateless_B_event'])} Б/событие. Обычный V6 хуже V5 по размеру на всех четырёх корпусах. Это отрицательный результат проверенного дизайна, не доказательство невозможности другого V6.

{main}

Числа — полные тела кадров, Б/событие; HTTP/TLS/ACK загрузки и регистрация не входят в эту таблицу. Для честного сравнения V4/V5/V6 основной контракт — исторический V1 **без event_id**. Последняя колонка V6 сохраняет полный исходный V1, включая случайный UUID каждого события. Называть исторические 13 Б «полным V1 lossless» нельзя. Внутри своего явно указанного контракта V6 восстанавливает точные исходные JSON-байты, порядок полей, числовые значения и отрицательный ноль. Есть literal escape для нестандартного envelope/sent_at/форматирования.

`*` Replay восстанавливает конкретную SHA-256 цепочку синтетического генератора, передавая первый хеш/расхождения полностью. Это не подтверждённый алгоритм игрового поля. Клиентский reference при проверке предикции тоже вычисляет SHA-256. Ни полностью бесплатный hash path, ни возможность удалить все хеши не доказаны.

Сделано: статическая схема train202 и её бинарный компилятор, неизвестные формы с inline escape, присутствие полей через предвычисленные shape masks и отдельная bitmask-абляция, сессионные алиасы с epoch, колонковые integer/float/string-потоки, zstd-1/3 и LZ4, режим полного event_id. Все V4/V5 кадры в восьми сравниваемых выборках независимо пересчитаны и декодированы; SHA корпусов и старые итоговые размеры совпали. Новая проверка seed2601 не участвовала в компиляции схемы.

C-ядро целых совпало с Python в {native['integer_conformance_cases']} случаях, не вызывает аллокатор и проверяет вместимость буфера. Это **не полный нативный кодек и не доказательство Zero-GC Unity**. Синтетические измерения выполнены на macOS arm64. `adb devices -l` не обнаружил подключённых устройств. Телефон, IL2CPP/Burst и батарея не измерялись.

Рекомендация: не заменять V5 этим прототипом ради трафика. Использовать V6 как проверенный простой CPU-кандидат для будущего полного нативного порта; сначала подтвердить настоящий контракт идентификаторов и игрового хеша. Память и батарею нельзя объявлять улучшенными по одному тесту компрессора.

Воспроизведение: `06-experiments/README.md`. Детали: `01-architecture-v6.md`, `02-benchmark-results.md`, `03-cpu-and-battery-evaluation.md`, `04-field-costs.md`. Новые файлы только в transport-v6; SDK и V2–V5 не менялись.
''')

bench=['# Подробные измерения\n\nВсе размеры вычислены из results/bench-*.json. Данные синтетические, не production capture. Схема фиксируется на train202 (18 установок, drift — 12). Для test101/holdout1729 используются 6 установок, drift — 4. Исторический drift использует seed808; новый drift — seed1733. Пачки: backlog cap100, drift — прежние session/deadline30s/cap30. Это не доказательство такой же плотности пачек в живом матче.\n\n'+main]
for p in profiles:
    bench.append(f'\n## {p}\n')
    for label,r in data[p]['rows'].items():
        bench.append(f"\n{label}, фактический seed {r['seed']}: {r['events']} событий, {r['batches']} пачек, {r['sessions']} сессий. SHA-256 length-prefixed canonical source: `{r['corpus_sha256']}`. Новые shape-события: {r['new_shape_events']}.\n")
        bench.append(table(['V6 вариант','Тело Б/соб.','+регистрация алиасов','+схема на установку','+схема на сессию'],[[m,f(v['body_B_event']),f(v['with_alias_setup_B_event']),f(v['with_dynamic_schema_and_alias_B_event']),f(v['with_session_schema_and_alias_B_event'])] for m,v in r['V6'].items()]))
        bench.append(f"\nV4: {f(r['V4_zstd19_B_event'])}; V5: {f(r['V5_stateless_B_event'])}; независимо измерено {r['V4_measured_bytes']}/{r['V5_measured_bytes']} байт. У обоих выполнен полный encode/decode всех пачек, совпали canonical JSON и опубликованные размеры.\n")
        bench.append(f"\nFloat-значений: {r['floats']}, точно представимых в масштабе 100 с сохранением выбранных IEEE bits: {r['exact_two_decimals']}. Выбор f32/f64 делается по точной представимости значения в Python; исходный CLR float/double тип без дополнительного SDK-тега неизвестен.\n")
bench.append('''
## Честный учёт setup

`zstd1` — static descriptor, schema already provisioned with build/version; колонка +схема на установку включает descriptor (zstd-1) +8B подтверждения для каждой установки. +схема на сессию оплачивает эту регистрацию при каждой сессии. Данные одинаковы; разница между static и negotiated состоит в setup/состоянии сервера. Это симуляция exchange с реально сериализованными payload, не запущенный сетевой сервис.

`dynamic_schema` — более дорогой контроль без зарегистрированной схемы: все нужные формы inline в каждой пачке. Это НЕ тот же режим, что однократная negotiation. Отдельная колонка +схема на сессию для него показывает искусственную верхнюю надбавку; рекомендуемая session-negotiation оценивается по строке zstd1. `batch_local_aliases` сбрасывает контекстную таблицу каждую пачку; его меньший slot иногда экономит сотые Б в теле, но setup обычно уничтожает эту выгоду. UUID/session/app/device strings не исчезают бесплатно: их регистрация и ответы посчитаны отдельно.

Регистрация alias = epoch8 + настоящий zstd-1 JSON `[first_slot, records]`; ответ = epoch8 + varint(next_slot). Схема в benchmark setup — сжатый JSON descriptor; отдельно скомпилирован binary descriptor, но его меньшая цена не подменена задним числом в таблице. Ни app store asset transfer, ни storage/server index RAM не объявляются нулевыми. В приложении статическая таблица всё равно занимает место.

Не включены сеть HTTP/TLS, bearer credential, потери и дубли, ACK данных, серверное хранилище, distribution схемы через store. Для полной сетевой оценки нужны реальные batch cadence, replay/ACK и RTT. Старый V5 stateless не требует alias state, поэтому сравнивать только тёплые тела недостаточно.

`explicit_masks` хранит дополнительную явную битовую маску в каждом событии. Основной формат передаёт shape ID, чья таблица уже содержит точную маску присутствия и типы; повторять её оказывается лишним. Имена свойств не передаются на известных формах.

`hash_omission_nonlossless_B_event` в сырых JSON — только грубая не-lossless абляция с удалённым полем и inline новыми формами; не сопоставлять её с lossless вариантами как новый протокол. Основной проверенный сценарий восстановления хеша — replay с anchors, а не удаление поля.
''')
bench.append('\n## Проверка новым seed2601 и размером пачки\n\nНи схема, ни prior не переобучались. Сессии не смешиваются. cap100 здесь отличается от главного backlog сравнения именно границами сессий.\n')
bench.append(table(['Корпус','cap','Событий','Пачек','V6 тело','+алиасы','Replay*','Полный V1 IDs'],[[p,cap,row['events'],row['batches'],f(row['body_B_event']),f(row['with_aliases_B_event']),f(row['conditional_replay_B_event']),f(row['strict_ids_B_event'])] for p,rows in confirm.items() for cap,row in rows.items()]))
bench.append('\n## Артефакты схем\n\n'+table(['Корпус','Форм','JSON B','Бинарная таблица B','JSON negotiation B'],[[p,data[p]['shapes'],data[p]['schema_bytes'],compilation[p]['binary_bytes'],data[p]['schema_negotiation_bytes']] for p in profiles]))
bench.append('''
## Пределы статистики

Единица размера — сумма bytes / сумма events, не среднее Б/событие по пачкам. Целевые seed фиксированы заранее; после первого прохода добавлены проверяемый fixed-point и epoch, поэтому сохранённый iteration1.log не является финальным протоколом. Seed2601 добавлен как свежая проверка после этих изменений. Настройки не подбирались перебором на holdout. CPU samples небольшие, без доверительных интервалов; они исследовательские. Преимущество по батарее не выводится ни из размеров, ни из desktop timings.
''')
write('02-benchmark-results.md','\n'.join(bench))

arch='''
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
'''
write('01-architecture-v6.md',arch)

cpu=['''# CPU, память, GC и батарея

Доказательства ограничены средой macOS arm64. Измерения ниже не CPU-такты телефона. Время в микросекундах зависит от частоты/нагрузки/FFI; пересчитывать его в mobile cycles нельзя. Python allocation peaks не показывают C#/IL2CPP GC. Нативный compressor stage не является полным ingestion/encode/native SDK.

## Что измерено

C `mtb6_ints` читает caller-owned int64 array, вычисляет стоимость четырёх простых layouts и один раз пишет выбранный. Сложность O(n); до четырёх коротких проходов, без дерева context probabilities, SHA и кэша BLAKE2s. n<=500, output capacity проверяется до записи. Отдельного временного массива нет; O(1) рабочие scalar locals, output<=1+10*n. Используется clang `__int128` для проверки разности без signed overflow; порт в C#/Burst обязан заменить это проверкой переполнения, а не обрезанием.

''']
cpu.append(f"Сопоставлено {native['integer_conformance_cases']} целых колонок, включая крайние int64, ширину64, константы и случайные длины. Проверены маленькие output buffers. `nm -u` не содержит malloc/calloc/realloc/free; kernel не аллоцирует heap. Это свойство **только integer kernel**.\n")
cpu.append(table(['Корпус','n','Raw B','zstd1 B/µs','zstd19 B/µs','LZ4 B/µs','CCtx1/19 B','Python encode peak B'],[[p,row['events'],row['raw_bytes'],f"{row['native_zstd1_bytes']}/{f(row['native_zstd1_us'])}",f"{row['native_zstd19_bytes']}/{f(row['native_zstd19_us'])}",f"{row['native_lz4_block_bytes']}/{f(row['native_lz4_us'])}",f"{row['zstd1_CCtx_bytes']}/{row['zstd19_CCtx_bytes']}",row['python_full_encode_peak_bytes']] for p,row in native['rows'].items()]))
cpu.append('''
Таблица — выбранная большая пачка каждого профиля, одинаковый заранее подготовленный V6 raw buffer. CCtx переиспользуется; создание/FFI/Python preprocessing/canonical rendering вне compressor-stage сравнения. zstd19 здесь БЕЗ V4 dictionary, это не V4 benchmark. Python encode peak включает reference traversal/packing/compression/source rendering, но не startup registry; native allocator compression contexts tracemalloc не видит. LZ4 block bytes без V6 header; полная матрица LZ4 есть в 02. Ни memory peak, ни маленький compressor-stage не объявляются полной памятью транспорта.

''')
cpu.append(table(['Корпус','V6 Python encode ms/100 events','V5 Python encode ms/100 events','V6 decode ms/100 events','V5 decode ms/100 events'],[[p,f(statistics.median(t['encode_ms']/t['n']*100 for t in r['python_timings'][:3])),f(statistics.median(t['encode_ms']/t['events']*100 for t in r['V5_rerun'])),f(statistics.median(t['decode_ms']/t['n']*100 for t in r['python_timings'][:3])),f(statistics.median(t['decode_ms']/t['events']*100 for t in r['V5_rerun']))] for p,r in fresh.items()]))
cpu.append('''
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
''')
write('03-cpu-and-battery-evaluation.md','\n'.join(cpu))

fields=['''# Стоимость полей

JSON bytes здесь = quoted key + colon + value, без общей запятой/envelope; ts — внутренний integer ms, в реальном V1 occurred_at_client длиннее. Это разложение компонентов, не additive entropy attribution после компрессии. `event_id` включён в field census, хотя legacy comparison его исключает. Считать каждое поле отдельно после zstd и суммировать нельзя: зависимости между полями меняют результат.

Schema+alias payload: name/keys ноль байт на известных формах; session/device/origin ноль value bytes в event, но context-slot column и handshake остаются. event enum/shape mask, sequence/time и property values оплачиваются совместно в raw column streams. При unknown forms имена снова приходят inline. Для каждого поля ниже указан путь восстановления; точный compressed размер всего кадра — в 02.
''']
for p,r in fresh.items():
    rows=[]
    for k,v in r['field_json_bytes'].items():
        if k in ('session_id',*wire.DEVICE_KEYS):dest='alias record + shared slot column'
        elif k=='name':dest='compiled shape ID column'
        elif k=='event_id':dest='16B/value in full mode; excluded only by legacy contract'
        elif k in ('sequence','ts','session_elapsed_ms'):dest='integer/residual column'
        elif k=='properties.placed_state_hash':dest='binary32 distinct + indices; replay bit + anchors'
        elif k=='properties.app_version':dest='context ref if exact type/value; otherwise value column'
        elif k=='properties.wave_attempt_id':dest='attempt_id ref if exact; otherwise value column'
        elif k.startswith('properties.'):dest='key0 on known shape; typed value column'
        else:dest='typed column'
        raw=rawfields[p]['columns'].get(k,{}).get('B_event')
        rawtext=f(raw) if raw is not None else '0/ref or shared'
        if k=='event_id':rawtext='16 (full mode)'
        rows.append([k,v['occurrences'],f(v['B_event']),rawtext,dest])
    fields.append(f'\n## {p}, holdout\n\n'+table(['Поле','Значений','JSON component B/event','V6 raw values B/event','V6 schema+aliases'],rows))
fields.append('\nShared shape/context/time/sequence/extension raw B/event: '+', '.join(p+'='+f(rawfields[p]['columns']['shared_shapes_context_time_sequence_and_extensions']['B_event']) for p in profiles)+'. Сумма всех raw columns и shared metadata проверена assert против encode_raw.\n')
fields.append('''
Размер отдельного поля в готовом compressed кадре не уникален: удаление поля меняет схемы, словари и компрессор. Поэтому raw census не выдаётся за «точно6.06Б энтропии». Чистая практическая разница baseline/replay дана на одинаковых событиях с одинаковой рамкой в 02. UUID seed хеша, самого поля и IDs после удаления не магически восстанавливаются. Никаких несуществующих player_id/device_id колонок в корпус не добавлено.
''')
write('04-field-costs.md','\n'.join(fields))
print('Exported five Transport V6 reports')
