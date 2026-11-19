# MTB5 context-v1: спецификация исследовательского кандидата

[статус] Исполненные references: frame_v5.py,context_codec.py,range_coder.py,model.py. Это не порт в UnitySDK/Go и не включённый endpoint. Ни одно указание из входного REPORT не разрешает терять данные, менять SDK или считать серверные ресурсы бесконечными.

## 1. Область и invariant

Сохраняется фактическое V1 JSON тело побайтово, кроме явно разрешённого удаления event_id иоговорённого immutable-origin slot. Реальные queued bytes остаются до durable ACK. Экспериментальный render поумолчанию использует V4 Python oracle и V1-minus-id; actualsource может быть передан явно. Именно source, ане CLR значение до JSONObject, является byte oracle. Полный захват Unity→JSONObject→SQLite передвнедрением остаётся обязательным.

V5 не зависит от zstd какалгоритм. При неподходящем model/field/source/profile budget клиент сохраняет исходные V1 rows ииспользует согласованный V4 либо исходный V1 с legacy UUID. Нельзя просто отправить research V1-minus-id встарый V1 endpoint, который требует event_id. Bridge legacyID↔origin/sequence иобщий content digest нужны до включения.

Один immutable origin на request; origin записывается при создании rows и resetIdentity его не меняет. Endpoint/project/credential разрешают этот origin server-side до дорогого decode. Реальныйпроект задаёт authcontext; данный standalone reference привязан ксинтетическому PROJECT_ID Mortris. Полный multi-project/SDK envelope adapter пока не внедрён.

## 2. Request frame

```
u8 header               0x51=context stateless,0x52=context stateful; остальные reject
u8 flags                bit0=source overlay,bit1=synthetic hash rule; остальные0
u model_id              1..127, immutable project registry ID
u n                     1..500
u source_byte_length    1..2097152
uuid16 origin           RFC/network byte order, canonical lowercase string onrender
if header==0x52: bytes16 base_state_id
bytes range_stream      до последних4байт
u32LE source_crc32      CRC32 exact reconstructed source
```

u — canonical uint64 LEB128≤10bytes, последний≤1,overlong reject (V4Reader). MaxHTTP body262144 Б. Нет magic zstd,нет compression window. Model ID с manifestSHA проверяется до decode; известный ID никогда не означаетдругие bytes. Source length ограничиваетвыход; n сверяется слогическим core и source JSON. CRC не является MAC,не заменяет TLS/auth/content SHA ине доказывает state identity.

Stateless всегда клонирует immutable prior исбрасывает last values. Stateful требуетточно указанный base snapshot, проверяет 128bit state ID дорасшифровки range stream. Origin предварительно помещается в last[install], поэтомутело его повторно не кодирует. Измодели неизвестнойбазы нельзя«попробовать угадать»:409/no-write →stateless re-encode с темиже event keys.

Limits research decoder: максимум 20 млн binary decisions, более строгий budget min(20M,8192+16×source_len); literal-byte budget min(4MiB,8192+2×source_len); defaultdeadline5 с, проверяетсякаждые 512 решений. Отдельные text chunks≤65536bytes, property string≤1024,property keys/names ASCII snake_case≤64,properties≤32 и 8KiB,sequencepositiveSQLiteint64. Metadata индивидуально можетнепоместиться в compact profile: исходные bytes неусекаются,нужен fallback/split. Общие process/tenant/cache/concurrency quotas остаются обязательны.

## 3. Версионированная модель и context ID

Probability table содержит 2×uint16 на slot,2^14slots=65536 Б. Начальные p_fast,p_slow32768. Каждый bit ctx получает slot=LE64(BLAKE2s-64(context_bytes,person=`MTB5ctx` снулевым padding до 8 байт)) &16383. Коллизии намеренноразделяютсчётчики,не теряютданные,поскольку index одинаков у encoder/decoder. Python saltedhash неиспользуется.

context_bytes рекурсивен: None=00;string=01,u UTF8/WTF8 length,bytes;integer=02,u ZigZag;tuple=03,u item_count,child encodings. Int context values невелики; operand order/role-string/позиция являютсячастью ABI. Полный списокконструкторов ctx зафиксирован в context_codec.py иего source hash; независимыйпорт обязан совпасть сканоническим vector ниже,а не выбиратьновый hash.

```
{
  "value": "(('tap', 'value'), 'M', 17, 8)",
  "canonical_bytes_hex": "030403020103746170010576616c756501014d02220210",
  "hash_u64": 2478455496967205034,
  "slot14": 12458
}
```

Raw prior: ASCII MTB5P1,u8 bits,u8 stateflag0,u JSON_length,4×2^bits probability bytesLE,typed JSON. JSON содержит ordered entries tables и EMA; state snapshot flag1 дополнительно last. Derivedtidx/table counts вычисляютсяиз tables. Typed values:0None,1bool,2integer decimalstring,3string,4tuple,5list,6dict ordered key/valuepairs,7float64LEhex,8Decimal lexicalstring. JSONensure_ascii/separators запятые/двоеточия безпробелов. Снимкине pickle;model artifact — zlib9(raw snapshot),bounded load с pinnedSHA256 и EOF/trailing checks. Загрузка неисполняет code. Compressed/raw SHA иразмеры 4 профилей естьв model-manifest.json; профили — отдельные build scenarios.

Максимум 65536aux mapentries,8192admitted tablevalues,1MiB theirUTF8bytes,serializedmetadata≤4MiB. Probability table фиксирована,но auxiliary model state не бесплатный. Prior+mutable clone обычно требуютдве probability tables. Python-only LRU context hashcache ограничен 32768entries иневходит в wire/logicalstate. Deployment обязанучестьего RAM/CPU либо реализоватьточно тотже hash безэтогокэша.

C#port долженсчитать Unicode scalar/codepoint length ссохранением unpaired surrogates,как Pythonlen,ане blindstring.Length UTF16. Internal string bytes — UTF8,с surrogatepass длянепарных codeunits; JSONsource можетиметьсвои escape forms,которые сохраняет overlay. Orderedproperties и orderedstate maps обязательны: обычный Go map iteration/неоговорённая CLR Dictionary enumeration неявляются ABI.

## 4. Binary arithmetic coder

Начальные range=0xffffffff,low=0,cache=0,pending=1. p=clamp((p_fast+p_slow)>>1,32,65504),bound=(range>>16)×p. bit0:range=bound;bit1:low+=bound,range-=bound. Обновления bit0:pf+=(65536-pf)>>4,ps+=(65536-ps)>>7;bit1:pf-=pf>>4,ps-=ps>>7. При range<2^24 выполняются byte normalization и carry cache,точныйалгоритм range_coder.py;independentrange_native.c подтверждает bytes/counters.

Termination выбирает value внутри[low,low+range−1] смаксимальнымчислом low zero bits,затем 5shiftlow,снимает initialcache0 byte и trailing zeros. Decoder читает 4initialbytes,недостающийхвостлогически 0. Поэтому V5 re-emits decodeddecisions вспомогательным encoder и MUST требуетполноеравенство canonical stream,включаядлину. Этоустраняетпринимаемыевпрототипелишние bytes. Server CPU/буфер shadow encoder входятвбюджет;оптимизация stream comparison возможнатолькос conformance test.

Small symbol кодируется fixed binarytree заданнойширины. uint:сначала 7modelledbits bit_length L,потом L−1 нижнихбитс implicit leading1;L0 означает 0,L>70 ошибка. Context длямантиссызависитот L,позиции/короткогопрефикса (точнаяветкав uint source — ABI). sint=ZigZag arbitrary residual≤70bits,domainvalues отдельно checked. C#/Go port должен реализовать multiword arithmetic/residual escape битвбит;нельзяпереполнить Int64 инеобоснованнопредполагатьдоступность UInt128 в Unity.

## 5. Event token order и predictors

Тело содержит n,затемкаждоесобытие вочередномпорядке:

1. Eventname model по previousname;sessionstring;ts initialuint или signeddelta контекст(previousname,name).
2. elapsed initialsigned либо residual:еслитотжесессионный ID,выбормежду prev_elapsed+dt и linear2prev−prevprev,по integerEMA.
3. sequence initialuint или prev+1+signedgap,систиннымисохраняемыми gaps.
4. Шесть device strings вфиксированномпорядке app_version,build_number,platform,os_version,device_class,locale;timezone initialsigned/previousdelta.
5. Orderedshape keys:bit«same aslastshape forname»;иначе count≤32,keys через stringmodel в order. Type каждого value кодируется 3bit symbol (None,bool,int,F32,F64,str,Decimal).
6. Все values впорядке keys;затем sent_delta signed после last event. Это **реальный** sent_at−lastts из source,decode егоиспользует.

Integerfield=(name,key),knownvalues учитывают last_by_key,last_by_(name,key),timestamp ипредыдущий event. Кандидаты: last;lastsameName;last+(ts−previousKeyTs);2last−previousKeyValue;eventdt;bestpartner value прошлого event. Argmin(EMA,index) однозначен. EMA←EMA+floor((16×bit_length(abs(error))−EMA)/4). Для partner score s←s−ceil(s/10)+1024×match,максимальный score,при tie ранний key order. Впереносенуженматематический floor,не C#/Go truncation division. Всерасчётыцелочисленные;floatEMA изпрототипаудалена.

Stringoptions:equal last key/last field;alias previousstring property;prior/local tableindex;UUID128bits;lowercaseevenhexbitstream;extension;prefix/suffix/substitutionedit;UTF8 order1text. Textbitcontexts используют prevbyte,runclass и binarytreenode;node/runupdate зафиксированыкодом. Tableadmission:≤255perfield,Pythoncodepointlength≤48,плюс globalbudgets. CRC/sourcecomparison проверяютполнуюобратимость,неразрешают discard неугаданного value.

F32 выбираетсятолькоесли finitevalue точнопредставимв float32;иначе F64. Sign/exponent кодируется uint,мантисса MSBbitstream23/52bits. Equal-cache проверяет IEEE64bytes,поэтому−0/+0 различимы. Decimal сохраняетсякак finite исходныйстроковый token. Нельзяквантовать float,терятьцифры Decimal илимолчанормализоватьчисловой sourcelexeme.

Syntheticflaghashrule:лишьпри knownlower64hexprev и placement_resolved/outcomeplaced предполагается SHA256(UTF8prevhex‖byteblock_id‖bytecell_x‖bytecell_y);прочиесобытиямогутповторять hash. Prediction используетсялишьпосле encoder equalitycheck,иначе literal;первое/mismatch/reset значениеякорь. Реальнаяиграэтоправилонеподтвердила,в primaryresultsflag0.

## 6. Exact source overlay и валидация

Canonicalhelper собирает V1-minus-idbody,включаядекодированный sent_delta. Если source отличается,flags.bit0=1 ивконцепотокадобавляется bytes_o1(source_overlay, patch) из V4exact.overlay. Patch содержит orderednonoverlapspans delete/insert относительно base. После apply проверяются source_len,CRC,JSONduplicatekeys,origin/project/schema,types/domain/propertybounds,sequence/n. Source sequence обязанравняться core identity. Всеэкранирования/порядок/лексемысохраняются;render необъявленподтверждённым Unityoracle.

Overlaychunk покаограничен 64KiB. Dense lexicaldifferences могутстоитьдорогов SequenceMatcher;input осталсяв queue,при budget/timeout нужен V4literal/старый V1fallback. Source validator повторяетосновныеграницы SDK,нонеявляетсяреальным Go middleware и auth service. Datetime/Unicode/HTMLescaping должныбытьсверенысреальным wirecapture.

## 7. State,ACK и durable identity

Defaultstateless не требует liveper-originservermodel. Приошибке,CRC,canonical/domain/deadlineexception никакихизменений liveprior/base не происходит:decode работаетна clone.

Experimentalstateful имеет BLAKE2s128base ID(person`MTB5stat`) отсериализованногополного typedstate (probabilities,tables,EMA,last). Server проверяетразрешённый origin/base,decodecandidate,проверяет statebudget **до DBcommit**,втранзакциисохраняетполный eventsourcedata и per-eventcontent digest,затемпубликует poststate и ACK. Client публикует candidate толькопослеправильного ACK того immutableHTTPrequest. Один in-flight на origin;lateACK закрытого token игнорируется. PartialACK модельнеделала:production должен resetstate/fallback либоявноспецифицировать postmodel для accepted/rejectedrecords.

Content identity/digest остаются V4:project,immutableorigin,sequence иполный SHA256 каноническогособытия,domain`MTB4-event-v1` безсменыиз-за V5encoding. Исключаются event_id и batch-levelsent_at,не eventfields. Иначе retryV4↔V5 создалбы falseconflict. Range-onlydedup и CRC вместо contentdigest недопустимы.

Экспериментальный ACK18 Б=`50 01`+post-stateID16. HTTPcallback привязанк immutabletupleprimaryrowIDs/requesttoken; ACK простоотчужого latestbatch неудаляет rows. StatelessnormalACK можетоставаться 2 Бкак V4; модель recovery явнооценивает 18 Б statefulACK. Этоработающий SQLite/requestsimulator,анепорт HttpClient/JNI.

Servercachemiss/restart→409beforewrites,clientstatelessresend сигнорированием lateACK,per-eventdurablededup непишетдубликаты. Старые bases/responsecache нужныпокаожидается retry;boundedLRU можетихвытеснить,тогдаплатится fallback. При orModel ID/SHA подменеоперацияничегонеподтверждает. State изодного JSON событийобычноневосстановим:runtimefloat/Decimaltags и overlaydecisions утеряны. Полный snapshot/codec transcript или statelessfallback обязательны.

## 8. Conformance fixture

[измерено]20base101events;frame/source/prior/poststate и statefulnextframe в results. Разные PYTHONHASHSEED1/2/random далиодинаковые decodedsourcehash/stateID. Размер frame378 Б,20events. Полный hex:

```text
51 00 01 14 9a 75 e8 8b 75 91 31 db 4e 32 98 dc b3 5f 94 c6 62 cd 13 d2 f3 19 d8 d4 83 fa 0d eb d3 b4 1a c5 75 0d 70 05 69 7e 00 a6 c7 e8 06 dc b5 a3 0f b5 b8 77 f1 25 d1 af 86 3e 27 c5 c6 f3 87 63 29 db d1 1a 38 6a fd 84 e1 f9 8b 30 09 5d df ea eb 94 da a1 1e 0b 47 55 7d 81 8f 10 aa 58 ca 34 06 48 27 d3 26 1f b7 74 10 1b df a5 05 b6 94 28 b4 cd 21 c8 e8 a9 7f 33 6d 18 6b 22 99 e1 ba 00 f7 b2 3c bc 64 a3 71 58 51 4d a1 e9 46 c6 bc 30 79 19 1a 5c 23 81 7b 4b 73 5f 3b 1c 5c 60 2a 78 20 e4 e1 50 09 80 4e ca c8 9b f1 7d 7e ec 3b ea c8 9f 42 68 8b a4 4f eb d2 2c 90 dd 06 9a 6c bd a7 52 e6 0e fe 67 bd 34 d3 6f 1d 1c ab da f4 09 10 89 93 25 f1 b7 ba a0 0c 2c 03 a4 2c c2 37 61 d7 1a f3 02 d2 f8 f1 ba e0 ef 0f d3 f9 99 63 cc 7d 21 5a 51 d7 8b ec 13 41 eb 77 f6 5c 75 f0 4b 23 c5 fe f8 1c 3b 1f 30 97 47 12 da c7 6d 8f 7f a0 4b 9b 7c 57 84 0d a4 28 44 7f b2 6d 73 70 fc 9a f5 d1 dc 20 bc 1f d8 aa 3c 13 fc f3 b7 fb 82 7e d4 09 d0 c0 e9 9c 4e 65 da 46 85 ee 7d 8f 14 a9 7a 66 b6 dd 49 a2 fa 3b d2 78 47 28 d8 8e 2f be 15 40 0c bf f6 c9 5a a0 98 28 50 67 f6 df 50 93 58 4d 0b 3c ad aa 98 a9 0f ba 71 b9 85 b0 76 0d 5b b0 c0 fb 34 53 f6
```
