# Transport V3: MTB3

[оценка] Спецификация исследовательского кандидата, не выпущенный SDK. Нормативные MUST/SHOULD ниже — требования будущей реализации. Экспериментальные `frame.py`, `codec.py` проверяют рамку и выбор безопасного подмножества, не заменяют hardened реализацию.

## 1. Контракт и варианты

Рекомендуемый V3 сохраняет MTB2 колонки, увеличивает заранее установленный словарь до64KiB, обучает его на **целевом размере пачки**, добавляет строгую рамку с длиной и точный literal escape. Истории между запросами нет. Базовая точка — прежняя cadence; cap100 используется для доступной очереди или при согласованном deadline60/120с. Explicit Flush/background отправляют немедленно. Предел500 только отдельный эксперимент, не рекомендация.

Для каждого события сохраняются все значения, порядок, временные поля, sequence; `event_id` заменяется `(project, immutable_origin_epoch, sequence)` и может отсутствовать. Других потерь данных нет. Сериализация принимается byte-exact относительно **фактического V1 тела**, исключая явно удалённые члены event_id; экранирование, порядок и числовые лексемы не нормализуются молча. Если columnar reconstruction отличается хотя бы байтом, MUST выбрать literal kind0. Literal MAY сохранять event_id; удаление UUID является разрешением, не обязательством. Это дороже, зато не зависит от особенностей .NET/JSONObject.

Исходные queue rows хранятся до durable ack, упаковываются только при отправке. `origin_epoch` сохраняется на строку при создании, его нельзя переписывать при resetIdentity. Один origin на пачку; credential может поменяться и должен иметь серверное разрешение на этот origin. В payload1 UUID install slot несёт immutable origin; в literal это envelope install_id. В обычном случае они совпадают с установкой V1. Изменение значения install_id после reset в восстановленном историческом V1 является дополнительным **явно оговорённым отличием**: там используется origin, а текущий credential-install остаётся только в авторизации. Группировка очереди по origin не должна ломать порядок внутри origin.

## 2. Согласование и HTTP

TLS, POST `/v3/b`, `Authorization: Bearer ...`, `Content-Type: application/octet-stream`, `Content-Length`. Внешний Content-Encoding не задан; промежуточный HTTP middleware не распаковывает рамку. Максимальный HTTP body262144Б; сырой payload2097152Б; событий500 (клиент обычно100). Сервер проверяет auth/rate limits до распаковки. HTTP/1.1 keep-alive или HTTP/2 при доступности; H3 не требуется.

Register/policy возвращает capability:

```json
{"transport":{"v3":{"path":"/v3/b","dicts":[{"id":1,"sha256":"<64 lowercase hex>","bytes":65536}],"max_frame":262144,"max_raw":2097152,"max_events":500,"kinds":[0,1]}}}
```

ID локален неизменяемому реестру проекта, диапазон1..127 для этого профиля; 0 означает отсутствие. Клиент выбирает только известный поддержанный ID с проверенным SHA256. Сервер без нужного ID отвечает409 UNKNOWN_DICTIONARY **до записи**; клиент повторяет stateless без словаря либо V1 с тем же ключом. 404/405 выключают V3; 401 требует credential recovery, 413 деления пачки, 429/503 backoff/Retry-After. Ошибка decode400 не удаляет очередь: literal/V1 retry, при повторном отказе durable quarantine и диагностика. Нельзя бесконечно повторять deterministic bad frame без backoff.

Регистрация нужна для bootstrap credential и не может целиком исчезнуть. После неё batch response может нести policy и credential refresh; действительный credential не требует отдельного periodic register. В idle нет batch, поэтому минимальный policy poll по deadline остаётся.

## 3. Внешняя рамка

```
u8 header = 0x30 | codec    codec0 raw, 1 gzip(RFC1952), 2 magicless zstd
u8 kind                    0 literal JSON; 1 revised MTB2; 2 experimental rules
uvarint dict_id            0..127; codec0/1 требуют0
uvarint raw_len            1..2097152
bytes encoded_payload      до конца HTTP body
```

Uvarint — canonical unsigned LEB128 ≤10байт, 10-й байт≤1, диапазон≤2^64−1. Overlong encoding отвергается. Для текущих словарей header занимает5байт при raw_len128..16383,6байт при большем. В body benchmarks V2 включён его2-байтный префикс; V3 включена эта рамка. Размер словаря не передаётся на каждый запрос.

Codec2: RFC8878 frame без4байт magic, без checksum/content size/dictID; словарь определяется внешним ID. Для предварительного чтения параметров decoder логически добавляет magic `28 b5 2f fd`; content size, если присутствует, MUST равняться raw_len, window≤2MiB. Ровно один frame, trailing bytes/concatenation запрещены. Decoder выделяет не более raw_len+bounded scratch, ограничивает CPU. Для gzip проверить EOF, CRC и отсутствие второго member/trailing; распаковка ограничена raw_len+1. TLS обеспечивает целостность канала, checksum не заменяет лимиты.

Encoder MAY выбрать кратчайший из raw/gzip/zstd(no dict)/zstd(dict), считая **полную** длину рамки. В эксперименте это4 прогона; для устройства можно использовать выбор по validation corpus и raw-if-expanded, только после проверки цены CPU. Уровень19 — измеренный ориентир, не обязательный ABI; более дешёвые3/9 допускаются после Android теста.

## 4. Kind0: точный literal

Payload — валидный UTF8 V1 batch JSON с исходными event objects, sequence и metadata; event_id MAY присутствовать. Numeric lexemes/escaped strings/order сохраняются как исходные bytes. Клиент может убрать event_id только lexical parser'ом с точными member spans, не parse→serialize с изменением чисел. Duplicate JSON keys MUST отвергаться. Envelope project_id соответствует auth; install_id соответствует разрешённому origin. Граница доверия повторяет `EventValidator`, кроме разрешённого опционального event_id. Строки, дошедшие из CLR с непарными суррогатами, трактуются так, как **уже записал их действующий V1 путь**; V3 не обещает восстановить несуществующие UTF8 bytes.

## 5. Kind1: полное описание payload

Двоичный layout соответствует `../transport-v2/01-protocol-spec.md` §5 с уточнениями ниже. Для реализации все поля перечислены здесь. Примитивы: unsigned LEB128 выше; signed int64 ZigZag `(n<<1) XOR (n>>63)`; string=LEB byte length+valid UTF8; UUID16=RFC byte order (не Guid.ToByteArray mixed endian); IEEE754 LE для f32/f64. Все арифметические операции checked, все индексы проверяются до доступа.

```
header:
  u8 payload_version=2
  u flags=1                          UUID origin обязателен, прочие биты0
  uuid16 origin_epoch
  u first_sequence
  u n                                1..500
  u gap_count                        ≤n−1
  gap_count × (u index,u skip)        уникальные возрастающие index1..n−1, skip≥1
  u base_time_ms
  s sent_delta_ms                    реальный sent_at−последний ts

tables:
  u ns; ns × (u byte_len, bytes UTF8)
  u nu; nu × uuid16
  u nh; nh × (u byte_len, bytes)      lower-hex значения, hex восстанавливается lowercase
meta:
  u project_string_index
  u sdk_name_string_index
  u sdk_version_string_index
contexts:
  u nc; nc × {
    u8 kind=0
    uuid16 session_id
    6×u string_index                 app_version,build_number,platform,os_version,device_class,locale
    s timezone_offset_minutes
  }
shapes:
  u nsh; nsh × {
    u8 kind=0
    u event_name_string_index
    u nf                             0..32
    nf × (u key_string_index,u8 type[,u alias_index])
  }
column_directory:
  u ncol
  ncol × (u key_string_index,u8 type[,u8 integer_mode])
body:
  n × u shape_index
  (u context_index,u positive_run_length)*  сумма=n
  n × s dt_ms                        ts[i]−ts[i−1], prev_ts=base_time, dt[0]=0
  n × s elapsed_residual             первое значение на context буквально;
                                     далее elapsed[i]−elapsed[prev]−(ts[i]−ts[prev])
  значения columns в порядке directory; внутри — по исходному порядку событий
```

Sequence[0]=first; далее prev+1+skip(index), в пределах1..2^63−1 действующего Android SQLite, без повторов. Восстановление ts и sent_at checked в допустимом диапазоне дат V1. Clock rollback допустим через signed dt. Elapsed не выводится без остатка: паузы и clock drift не теряются.

Типы:

| tag | Колонка |
|---:|---|
| 0 INT | mode0=signed int64; mode1=delta от предыдущего значения той же (key,type) колонки, prev=0 |
| 1 STR | u string table index |
| 2 BOOL | u8 строго0/1 |
| 3 F32 |4байт IEEE754, конечный |
| 4 F64 |8байт IEEE754, конечный |
| 5 UUID |u uuid table index; только lowercase canonical string |
| 6 HEX |u hex table index; только lowercase even hex длина≥16символов |
| 7 NULL |нет данных |
| 8 ALIAS |u alias_index в shape descriptor, только строго более раннее поле; нет column data |
| 9 CTXREF |одноимённое поле текущего context; нет column data |
| 10 U64 |u, только значение>int64.max, ≤uint64.max |
| 11 NUMTEXT |u string index; исходная конечная десятичная числовая лексема/decimal scale |

Форма определяется именем+**упорядоченными** key/type; ключи не повторяются. Алиас разрешён только при одинаковой исходной лексеме и типе во всех событиях формы; CTXREF требует того же. Нельзя alias120.0→120 или true→1. Ключ с разными типами даёт разные колонки. Число значений каждой колонки определяется формами; directory обязан описывать каждую data-bearing пару ровно один раз, лишних/повторных колонок нет. Decoder потребляет payload полностью.

Strings/uuid/hex назначаются в порядке первого использования кодировщиком; для чтения достаточно индексов, но conformance corpus фиксирует порядок. Context и shape содержат inline данные, CAS ссылки запрещены. RLE run не0; alias cycle/forward ref невозможны. Все nf/nc/nsh/strings ограничены и совокупно raw_len; ключи ASCII snake_case≤64, строки properties≤1024Б, свойства≤8KiB, число полей≤32. Value domain после decode повторно валидируется.

Сборка V1: envelope metadata из payload, SDK/context поля в исходном порядке, свойства в shape order, sequence; все временные ISO строки UTC с3цифрами миллисекунд. Для float/double текст берётся только если гарантирован исходный V1 lexeme, иначе NUMTEXT/literal. Signed zero сохраняется. Encoder сравнивает с реальным исходным телом и при расхождении выбирает kind0. Исследовательский codec.py исправляет DBL_MAX и отключает type-unsafe CTXREF, но не содержит настоящего Unity capture oracle: его тесты не снимают этого требования.

## 6. Identity, запись и ack

До включения V3 сервер V1 MUST сохранять `(project,origin,sequence) ↔ legacy_event_id` и digest content. Если это невозможно для ранее принятых событий, сохранить legacy UUID в переходном literal либо дождаться подтверждения всей старой очереди; включение нового dedup без этого моста запрещено.

Digest считается на отдельное immutable событие, исключая event_id; batch sent_at, границы пачки, credential и codec в него не входят. Повторная упаковка и новое время отправки не должны вызывать conflict. Правило канонизации digest фиксируется отдельно от JSON framing и сохраняет все числовые значения/строки; тестируется на переходе V1/V3. В одной транзакции сервер проверяет уникальный event_key и SHA256 содержимого **с учётом согласованного исключения event_id**, записывает событие и dedup record. Для дубликата с тем же содержимым ack повторяется. Тот же ключ с другим содержимым → conflict без overwrite/ack; очередь сохраняется для repair. CRC32 не подходит для надёжного обнаружения подмены. Normal install с новой пустой DB получает новую epoch; восстановленная/клонированная DB не должна самовольно переиспользовать старую epoch для новых событий после обнаруженного divergence. Для reset/переноса сервер выдаёт разрешённую связь credential→старые origins, не доверяет origin строке без auth. Dedup retention охватывает весь offline/retry horizon; удаление tombstones требует отдельного доказательства.

ACK привязан к конкретному HTTP request/stream и immutable списку отправленных queue rows:

```
u8 control: high_nibble=3; bit3=extensions; bits0..2=status
u policy_epoch
if status=1: u exception_count; exception_count×(u event_index,u reason)
if extensions: u ext_bytes; ext_bytes TLVs=(u type,u len,bytes)
```

Status0=все события durable accepted/duplicates. Status1=все, кроме перечисленных exception индексов, durable accepted. Reason1=retry,2=terminal-invalid (локальная durable quarantine),3=identity conflict (не удалять). Status2=вся пачка conflict,3=decode retry; статус2/3 ничего не подтверждает. Индексы unique ascending <n; malformed/неизвестный status ничего не подтверждает. Ack0 при epoch0..127 **2байта** (`30 01` для epoch1), не требует echo диапазона — контекст известен из HTTP запроса. На retry нельзя применить ack к новому списку строк.

Extensions: type1=policy UTF8 JSON, type2=server_time int64LE, type3=capabilities JSON, type4=credential-refresh JSON; неизвестные пропускаются по длине. Сервер включает policy при смене epoch; при idle poll остаётся. Данные auth/policy обрабатываются только после TLS и валидации. Потеря ack вызывает полный retry с теми же ключами; сервер повторно не пишет. Клиент удаляет только точно подтверждённые строки в SQLite-транзакции после проверки ack. Политика discard_pending — явная внешняя политика удаления, не следствие transport error.

## 7. Словари и stateful extension

Рекомендуется один64KiB словарь проекта/профиля в build, обученный на релевантных пачках, не глобальный обученный на секретах. Несколько словарей — только если paired cost оправдывает SDK/update budget. Immutable ID+SHA256; запрет подменять bytes под старым ID. Сервер принимает все ещё живые IDs; клиент выбирает новый только после server capability.

Обновление: TLS authenticated manifest с project, base SHA256, target SHA256, full size, patch size/version; при rollback threat подпись закреплённым release key и монотонная epoch. Patch=обычный zstd frame, old dictionary bytes как RAWCONTENT. Выход ограничен65536, проверяется SHA256 и размер, atomic rename; до успеха старый словарь остаётся. Bad base/patch/hash → full download или прежний словарь. При экономии sБ/событие update D окупится только после D/s событий. Такой же механизм возможен для probability tables, с отдельным immutable model_id и спецификацией точной целочисленной арифметики; модели по float inference запрещены без доказательства bit identity на платформах.

История между пачками в рекомендацию не включена. Опциональный будущий stateful mode обязан ссылаться на **acknowledged** snapshot SHA256/truncated128, decoder не продвигает историю на speculative/unacked запросе. Retry обрабатывает ту же ссылку; сервер сохраняет предыдущий snapshot до закрытия retry horizon. Cache miss→stateless resend; state не означает, что данные приняли. Именно этот recovery budget, а не просто процент идеального сжатия, решает окупаемость. Формат mode не выделен в v3 header, пока его не стандартизуют; слать его как kind1 нельзя.

## 8. Предельный эксперимент (kind2, не включать без отдельной capability)

Payload=`u rule_id=1 || MTB2_payload_with_transformed_hash_values`. После MTB2 decode сервер проходит события в исходном порядке. Для строки placed_state_hash:
- хеш первой записи/после несовпадения передаётся буквально;
- если placement_resolved outcome=placed и уже есть previous hash: predicted=SHA256(UTF8(previous lowercase hex)||u8(block_id)||u8(cell_x)||u8(cell_y)).hexdigest();
- иначе predicted=previous hash;
- литерал `=` означает predicted; любой другой литерал — новый hash; затем previous=восстановленный hash.

Контракт rule1 допускает только исходные lowercase64hex hash values, не строку `=`; границы block/cell0..255, overflow→literal. На несовпадении encoder MUST отправить литерал; decoder первой записи не принимает `=`. История только внутри пачки, поэтому каждый запрос самодостаточен. Декларативное обобщение — immutable rule manifest с типизированными operations copy/add/sub/xor/hash и полной equality guard; неизвестный rule ID→literal/V1 до записи. Нельзя скачивать и исполнять произвольный код. Сложность и лимит операций ограничены.

[измерено] Этот rule соответствует только `gen.py`, не утверждает эквивалентность настоящему Mortris hash. Экспериментальная рамка frame.py поддерживает kinds0/1/2; extreme.py + codec.restore выполняют полный roundtrip kind2; это proof-of-concept, не hardened decoder. Расход rule ID включён в extreme benchmark как1Б на пачку сверх обычной рамки. Полный replay намерений требует версионированной детерминированной игры, RNG и начальных state; неизвестные physical/device/clock inputs неизбежно требуют escape/residual. Это не универсальная SDK-оптимизация.

## 9. Сквозной hex-пример

[измерено] `06-experiments/extras.py`: seed101, первая установка, первые20 последовательных событий base, dict1=`dict64_base.bin` (SHA256 в extras.json). Полные исходные V1 bytes, payload и frame сохранены рядом. Пример показывает консервативную cadence, не средний размер100-событийных пачек. Полный hex и счётчик ниже генерируются из сохранённого бинарного frame.
<!--GENERATED-->

[измерено] V1 безevent_id 15002Б → payload 1559Б → frame 472Б = 23.60Б/event. Prefix `32 01 01 97 0c`: zstd,kind1,dict1,raw_len1559; header5Б, compressed body467Б. SHA256 frame `e9454f64f969a7b7e94e09d2f4f8f725dbddf94575730681ee57ad17bdf9b3ca`.

```text
0000  32 01 01 97 0c 00 08 75 0e 00 f3 95 56 dc 7b 9b
0010  db b7 2b 82 21 bc 05 36 0e 7c 68 97 22 7c b7 48
0020  97 5f 67 60 c2 85 bf 72 e3 01 ef 18 48 63 3c a6
0030  21 8b 8c 08 21 b3 ff 2e 79 2b 47 e9 51 38 eb 52
0040  88 68 59 ef d7 1b 49 a0 d6 bd bf 3f fe bd ed ef
0050  f5 4d 7f 7d 7d e5 58 7a d7 b2 92 25 81 0e 71 c2
0060  5a eb 7e 9d 70 5a eb 37 92 dc 43 9b 0b a8 95 6c
0070  f5 a3 66 0d d2 e0 1b 7b 45 ff e4 64 b3 e8 ec 8d
0080  85 bd e2 2e f1 02 a2 2e 4a 12 56 a3 fa 9a 51 d7
0090  97 3e 4e 41 b4 71 f3 77 56 86 4b 48 63 0b 50 d0
00a0  21 9d 2b f4 40 37 60 63 18 29 33 b6 c3 51 8c d4
00b0  e7 ca e6 0e 01 1d 80 16 28 8f 5c 24 92 96 04 ed
00c0  67 6a 40 ee 4e 20 46 4a 88 a4 7b 50 41 14 22 da
00d0  73 b5 f2 b9 ec f2 43 8f c2 a3 f0 61 a1 2c d0 b9
00e0  a1 33 74 a0 ba e8 07 c6 4e 3d 22 05 53 97 c4 21
00f0  57 c9 e1 c2 b8 cd c0 d2 8b 78 92 d4 28 89 0c 73
0100  24 55 15 7e a3 22 ab e2 69 e3 60 21 48 c3 8c 8a
0110  25 bd 19 06 8a 78 76 78 0a d4 bf 26 99 34 54 8a
0120  94 d0 b2 c7 f5 8a 21 fa 4d ad 85 64 49 6d 00 40
0130  85 95 65 55 25 05 20 43 86 0b 18 32 70 a8 b2 8a
0140  02 00 c0 2a 4a 43 06 2c 00 54 1c 36 58 e9 bc 5f
0150  db 16 1a 8c 8d 82 21 f2 ae 02 62 67 de 14 19 16
0160  29 1c 2b 6e 90 62 eb 25 fc ac 39 0d 00 40 a7 c5
0170  51 41 a9 47 e9 86 25 b9 87 f0 5d 7c 75 08 dc ec
0180  93 5c 62 f4 de 86 c9 ee e2 67 f2 a4 c7 44 40 3b
0190  21 4c 5b 21 4b 4b 28 2a 52 6b 0d 1e 37 97 79 48
01a0  57 7a 06 24 c6 6c 9a 87 27 e1 fe 0a 92 c0 37 a8
01b0  a5 43 64 84 4a 6e 21 f2 08 1a be 68 ca fe 88 1a
01c0  1a 6b a2 aa 17 a4 c4 bf de ec a6 cd 20 2c 68 e4
01d0  2c 42 91 3f 42 10 ed 12
```

[измерено] Восстановление: `.venv/bin/python extras.py`, либо `frame.unpack(example_frame,{1:dict}) → wire.mtb2_decode(payload) → wire.v1_json(...,without_event_id=True)`; сравнить с `results/example-v1.json`. Настоящий sent_at/SDK serializer проверяется отдельно на реальном корпусе, этот fixture использует V2 synthetic conventions.
