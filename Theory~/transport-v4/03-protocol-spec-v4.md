# MTB4: исследовательский wire-контракт

[статус] Это полный формат работающего Python reference, не выпущенная реализация SDK/сервера. Production MUST выполнять auth, domain validation и ресурсный контроль; research decoder не заменяет такой сервер. Номер4 не означает автоматическую миграцию на более сложный формат.

## 1. Инварианты и согласование

Восстанавливаются фактические V1 bytes, кроме явно разрешённого удаления event_id. Источник — уже записанный payload_json, не попытка восстановить потерянную CLR lexical форму после JSONObject. Порядок ключей, числа, -0, Unicode escapes, timestamps, elapsed, sequence/gaps сохраняются. Исходные строки не удаляются до durable ACK. Реальное sent_at берётся из отправляемого V1 source, не last_ts+250; синтетический core использует старое соглашение, а kind2 overlay исправляет любую lexical/envelope разницу до точных source bytes.

POST /v4/b over TLS, Bearer auth, application/octet-stream, никакого внешнего Content-Encoding. Capability MUST задавать version, max_frame262144, max_raw2097152, max_events500, supported kinds, dictionary ID→SHA256→size и компактный metadata/profile budget. Dictionary ID0=нет,1..127 immutable; нельзя заменять bytes под тем же ID. Missing dictionary→409 до любых записей, stateless/V1 retry с теми же identity. 401 credential recovery,413 split,429/503 bounded retry/backoff. Ошибка никогда не означает удаление очереди.

Профиль данного reference ограничивает raw+trailer ≤min(2097152,4096+n×8704). Это дополнительный согласуемый бюджет, **не предел всех допустимых строк нынешнего SDK**. Если metadata не помещается, клиент использует исходный V1, сохраняя очередь и diagnostic. Сервер MUST проверять разрешение на origin до decode, общий лимит конкурентных запросов, CPU/time budget и суммарный размер dictionary cache. Внешний n не является доверенным: сверяется с core и с events в реконструированном JSON до записи. Поддельный n=500 всё ещё может потребовать до2MiB; абсолютная quota обязательна.

## 2. Примитивы и outer frame

```
u8 header = 0x40 | codec           0 raw,1 gzip,2 magicless standard zstd
u8 kind                           0 literal,1 MTB4 core,2 exact-overlay capsule
u n                               1..500, до распаковки
u dict_id                         0..127, raw/gzip требуют0
u structured_raw_len              >0, bounded
u trailer_len                     bounded, включая raw tables
bytes compressed_structured       до последних trailer_len байт
bytes trailer                     ровно trailer_len
```

u=canonical unsigned LEB128 ≤64bit/10bytes, последний10й≤1; overlong запрещён. s=ZigZag int64. UUID16=RFC network order; IEEE754 little endian. Все length/index/арифметические операции checked. Неизвестные codec/kind/flags — ошибка. Source больше frame/raw budget делится по событиям; одиночное превышение отправляется старым V1 путём, без усечения.

Zstd сохраняет FHD+window descriptor, убирает только4байт magic. Content-size/checksum/dictID отключены encoder-ом. Decoder читает frame parameters с логическим magic prefix, требует window≤2MiB, известный content-size равен structured_raw_len. Ровно один frame, без trailing/concatenation. Однократная bounded decompression, никакого stream-reader списка всех chunks и join. Gzip проверяет eof, unused_data, unconsumed_tail, размер; flush без output cap запрещён. TLS обеспечивает integrity канала. Decodable mutations не являются разрешением доверять payload: parser/schema/auth validation остаются.

Pack сравнивает raw с одним выбранным zstd контекстом; экспериментальная adaptive=True может добавить gzip/no-dict. Полный header/trailer участвуют в выборе. Один повторно используемый context поддержан; одновременные операции на нём запрещены. Compressor level/таблицы не являются частью decoder semantics.

## 3. Kind1: порядок core

```
u8 core_version=4
u flags=1
uuid16 immutable_origin
u first_sequence; u n; u ngaps
ngaps × (u event_index,u skipped)   ascending unique 1..n-1, skipped>0
u base_ts_ms
s sent_delta_ms                    sent_at-last_ts
u8 separated_string_lengths        0/1
u8 external_binary_tables          0/1
u ns
if separated: ns×u byte_len; then all string bytes concatenated
else: ns×(u byte_len,bytes)
u nu; u nh; nh×u hex_byte_len
if not external: nu×uuid16; nh×hex bytes
u project_string_id;u sdk_name_id;u sdk_version_id
u nc
nc×(uuid16 session_id,6×u string_id,s timezone_offset_minutes)
u nsh
nsh×(u event_name_id,u nf,nf×(u key_id,u8 type[,u prior_field_index]))
int_vector[n] shape_id
int_vector[n] context_id
int_vector[n-1] dt_ms               first ts exactly base_ts
int_vector[n] elapsed_residual
value columns in derived order
```

Column order выводится обходом shapes в порядке первого появления, внутри — field order; каждая новая data-bearing (key,type) появляется один раз. ALIAS/CTXREF/NULL не имеют данных. Directory отсутствует. Количество значений каждой колонки вычисляется из shape_id событий; имена/ключи и порядок свойств сохраняются. Строковые/UUID/HEX таблицы назначаются encoder-ом в порядке первого использования; decoder использует индексы. Для варианта external trailer содержит только nu UUID16 и HEX bodies в табличном порядке, без дополнительного framing; длины в core. Session/origin и bitmap hash anchors не вынесены.

nc/nsh≤n, n1..500, nf≤32, ns/nu/nh≤16000, все индексы проверяются. Неиспользуемые shapes/колонки reference отвергает. Properties keys ASCII snake_case≤64; property strings≤1024 UTF8 bytes и serialized properties≤8192. Reference проверяет основные ограничения, но это не полная копия .NET/Go validator: production MUST валидировать весь source и metadata после восстановления. Старый generator elapsed=-1 допускается в исследовательском signed64 потоке; новый SDK Stopwatch oracle должен установить допустимую продуктовую область.

Строковый блок core использует UTF8 плюс внутренний surrogatepass для escaped lone-surrogate code units; это **не UTF8 текст HTTP**. При рендеринге lone surrogate становится валидным JSON escape, а kind2 сохраняет фактическую source лексему. Объединённая проверка UTF8 всего string block недостаточна для отдельных строк: границы и типы проверяются отдельно. Noncanonical numerical source исправляется overlay, не округлением.

## 4. Integer vector, float и value columns

Integer-vector знает n из структуры; при n=0 отсутствует целиком. Иначе mode byte:

|mode|Данные|
|---|---|
|0|n×s literal|
|1|n×s delta, prev=0|
|2|s minimum,u8 width, LSB bitpacked offsets|
|3|как2 для delta, prev=0|
|4|Elias–Fano: s minimum,u8 low_width,u high_bit_count,packed low[n],high bitmap|

EF только для nondecreasing входа. high bit position[i]=(value[i]-minimum)>>low_width + i; decoder вычитает i и комбинирует low bits. high_bit_count≤32000, width≤64, число установленных битов строго n, padding нулевой. Bitpack least-significant bit first, padded нулями. Прямой режим остаётся для произвольных int64 и перепадов, чья delta не помещается в int64. После восстановления проверяется domain. Encoder выбирает минимум **сырого потока с metadata**, а внешний paired benchmark проверяет, окупилось ли это после zstd.

|type|Данные|
|---|---|
|0 INT|integer-vector с известным count|
|1 STR|table-index vector ниже|
|2 BOOL|count бит, LSB first, bool ровно0/1|
|3 F32 /4 F64|float submode0/1/2|
|5 UUID /6 HEX|table-index vector|
|7 NULL|ничего|
|8 ALIAS|prior_field_index в shape, строго более раннее поле|
|9 CTXREF|одноимённое context поле, только exact lexical/type equality|
|10 U64|count×u, ≤uint64.max|
|11 NUMTEXT|table-index vector, Decimal исходной числовой лексемы|
|12 HASH_PRED|только placed_state_hash: count бит; на каждый0 —32 anchor bytes|

Table-index vector: u8 mode0 = integer-vector глобальных IDs; mode1 = u local_count, local_count×u global_id, integer-vector локальных IDs. Count выведен из форм, не приходит от value stream. Alias разрешён только при точном совпадении типа/исходной сериализации во всех событиях формы.

Float submode0=все значения raw IEEE bytes;1=u8 decimal_scale0..9 + integer-vector mantissas, decode m/10^scale и обязательный cast к F32/F64;2=XOR с предыдущим raw word, control=(trailing_zero_bytes<<4)|significant_bytes, далее только значащие bytes, prev=0. Нулевой XOR имеет control0. Все результаты finite; signed zero сохраняется. Scale-кандидат допускается только если IEEE bytes после восстановления совпадают; -0 не проходит через ошибочный mantissa0. Это собственные простые модели, **не Chimp128 или ALP paper implementation**. NUMTEXT не удалён.

HASH_PRED:1=вычислить SHA256(UTF8 previous lowercase64hex || byte block_id || byte cell_x || byte cell_y), только для placement_resolved/outcome=placed, иначе повтор previous hash. First/reset/mismatch=0+32 bytes. Все исходные хеши проверяются encoder-ом. Нет previous anchor→decode error. Обычный режим без этого game rule является универсальным. Реальный алгоритм игры не установлен.

Elapsed residual первого события контекста передаётся буквально; последующих = elapsed-current - (previous_elapsed + current_ts-previous_ts). Clock rollback сохраняется signed dt. Sequence positive increasing в SQLite int64, gaps сохраняются; overflow/error не может привести к ack.

## 5. Kind2: точная лексическая поправка

```
u core_len; bytes core
u8 patch_kind 0/1
if1:
  u source_length;u edit_count
  edit_count×(u base_start,u delete_length,u insert_length,bytes insert)
```

Позиции относительно реконструированного canonical base, ascending/nonoverlapping; вставки копируются в новый ограниченный output. Нельзя выйти за base/source limits, edit_count≤16000; decoder обязан исчерпать capsule. Patch сохраняет любые исходные lexical/envelope bytes, а не только свойства одного заранее выбранного типа. Encoder использует SequenceMatcher только при отличии source; dense mismatch может быть дорогим, поэтому literal kind0 остаётся. Сравниваются полные framed размеры обоих вариантов; при error fallback сохраняет исходный source.

Kind0 payload — точный V1 JSON, trailer пуст. Выход `transport.decode` — bytes; до записи сервер обязан отдельно проверить валидность JSON, duplicate keys, число events, sequence, project/origin authorization и SDK domain. Python request-path тест доказывает byte reconstruction, не всю серверную валидацию.

## 6. Identity и ACK

Ключ=(project,immutable origin_epoch,sequence), origin записывается на строку при создании и не меняется при resetIdentity. Credential server-side разрешён на этот origin. Восстановление/клон DB не получает право генерировать divergent events в прежнем origin; нужен обнаруживаемый conflict/rekey flow. V1 migration заранее сохраняет соответствие legacy event_id↔event key; если мост недоступен, старые события остаются на V1 до подтверждения.

`exact.canonical_event`: parse JSON с ordered object pairs, reject duplicate keys и NaN/Infinity; удалить только top-level event_id; игнорировать whitespace, декодировать string escapes и сериализовать строки ensure_ascii, сохранить порядок ключей и исходные number lexemes. Не сортировать свойства и не сводить120.00 к120.0: это дополнительные потери текущего строгого контракта. Включены **все** session/device/time/name/properties/sequence поля. SHA256 получает length-prefixed domain `MTB4-event-v1`, UTF8 project, canonical authorized origin, canonical event bytes. Batch sent_at, codec, boundaries и credential не участвуют. Одинаковый source при V1/kind0/kind1/kind2 даёт одинаковый digest; поле с изменённым содержимым — conflict. Для уже сохранённых legacy parsed events такой digest может быть невосстановим: миграционный gate обязателен.

Первая запись и identity/digest проверка — одна durable transaction; ACK после commit. Range/high-watermark и batch-hash cache разрешены только как горячая оптимизация над durable per-event evidence. При subset/rebatch/overlap проверяется cold event digest/содержимое. Удалять эту информацию ради32Б на пачку нельзя без нового доказательства. Retention должен покрывать фактический offline/retry horizon; его отсутствие сейчас не разрешает очистить tombstones по произвольному TTL.

```
u8 control = 0x40 | status    0 all accepted,1 exceptions,2 conflict,3 decode retry
u policy_epoch
if status1: u count;count×(u index,u reason)
```

Reasons1 retry,2 terminal invalid→durable quarantine,3 conflict→retain. Индексы strictly ascending < immutable request row count. Malformed/unknown status/trailing ничего не подтверждают. Epoch0..127 и status0=2байта. Изменение policy требует authenticated payload или отдельного policy fetch; idle poll сохраняется. Extension бит/TLV пока не реализован в модели, не отправлять самовольно.

Клиент связывает HTTP response callback с immutable request token и tuple queue primary keys, а не текущим latest batch или индексами живой очереди. Late response после закрытого timeout игнорируется; retry сохраняет те же event identities. Удаление только этих accepted row IDs в SQLite transaction. Модель `reliability.py` это проверяет, но не является реальным HttpClient/JNI портом. Внешний unkeyed16bit hash не добавляется: он не аутентифицирует, допускает коллизии и не включает gaps/content. При необходимости межсистемного ACK binding использовать полный request digest с достаточной стойкостью и отдельным согласованием, не заменяя immutable row binding.

## 7. Полный fixture

[измерено]20 events из base101, dict-base-trailer.bin, core/trailer/source и полный frame сохранены в results/example-*.bin/json. Размеры и hex ниже сгенерированы из фактического кадра; dict bytes доступны рядом.

Core 1290Б, trailer 144Б, HTTP body 527Б.

```text
42 01 14 01 8a 0a 90 01 00 08 95 0b 00 c3 8f 3b 5c 59 d6 ca 32 5d cb 62 63 0d 64 d4 07 48 f2 0d 37 d2 72 ce 32 4a 72 1d 25 65 64 d9 eb cd 9e 55 43 0a 73 4d eb c8 bf 43 94 31 79 17 1d 15 f2 c5 bf 19 59 63 1e aa 64 9d 89 85 ca cf 85 92 43 fc 94 a7 61 0c c6 92 44 b6 9a d6 a9 3b 8f 43 a7 b2 9e c7 19 3d fe e6 f1 ea 5c cb b4 9c 7a e4 cf 7e 96 b3 16 22 3b c8 72 0a 3d eb 77 be 65 dc 6a aa 3f 0e 15 da 82 f3 55 9d 9a 21 74 06 ef 3c 62 0b 69 ac a1 d3 06 a5 5e b4 2a f0 cd 0b 0f 4e 15 4e bd 23 df 38 35 4f dd c5 f2 cc dc 2a b6 2a 0a 85 00 11 b3 91 13 af 0d a9 2e 19 74 ff 93 31 8b af 82 42 b3 92 42 50 75 60 0a ca aa 43 87 33 0e 1d d2 a6 0e 3c 59 59 1d 78 f2 d0 01 81 95 54 1a da 01 29 ac cf 75 f4 bd 89 91 bb d5 2b 1c 1c ed 00 60 f2 05 2f aa 81 17 a8 1e 2b 74 78 56 7d 30 fc d3 42 93 91 06 2a ec 55 9f 4f 55 d8 f8 7c 4a 78 0f d5 28 2f 80 4b c0 f1 83 40 7e 73 7b 34 35 80 0a 21 51 e5 b5 89 f4 97 19 1c 85 21 09 bd 9a fc 42 1e ca 81 e0 85 44 f6 c1 04 cf 78 06 24 e6 4e 15 1e 7b 6c 70 b3 cc 0c d4 41 14 07 5d a1 34 20 fa 0f d0 0d 81 05 47 b5 30 4e cf 95 15 eb f6 cc 73 c4 6e 86 87 49 47 d8 d2 8d 00 db 53 14 38 e1 44 70 01 f7 11 ef 6c f7 45 7b 6b ea af 19 b1 a7 02 f2 12 e5 7b 43 09 9c df 6f ad d3 ff f5 d6 a6 2e 67 de ad 4d 7d 9a 2a 74 f9 7e a8 76 91 06 de d5 4e 33 89 16 34 31 25 ef c6 b9 0b b7 19 23 37 7d 88 ef 8a 0c d5 3f 11 c8 20 d2 cf b1 f2 06 ed a2 b8 f4 58 b0 8f 0f 15 55 cb 01 9e cd 0a 30 9f e7 d0 1b 35 fc 9c 22 1f b3 d3 9b 00 c6 5c c6 b3 71 94 a1 83 80 28 1e bb 27 6e 3c c2 cb df 39 49 17 d8 d9 1b e8 4a bd 97 4c f7 af 7b 01 65 e2 9a 75 dc a9 e2 e2 77 bc a7 3c f7 80 a3 0f 87 b3
```
