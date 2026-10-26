"""Publish measured V5, explicitly separated from the submitted prototype."""
import json
from pathlib import Path
R=Path(__file__).resolve().parent;D=R.parent
load=lambda n:json.loads((R/'results'/n).read_text())
profiles={p:load(f'bench-{p}.json') for p in ['base','rich','alt','drift']};memory=load('memory.json');network=load('network.json');miss=load('miss-cost.json');native=load('native-conformance.json');fixture=load('fixtures.json');compact=load('compact-prior.json')
def write(n,s):(D/n).write_text(s.strip()+'\n')
def table(head,rows):return '| '+' | '.join(head)+' |\n|'+'|'.join(['---']*len(head))+'|\n'+'\n'.join('| '+' | '.join(map(str,row))+' |' for row in rows)+'\n'
fresh=[]
for p,x in profiles.items():
 r=x['rows']['fresh_holdout'];a=r['V4_B_per_event'];b=r['stateless']['B_per_event'];c=r['stateful_ideal']['B_per_event'];fresh.append([p,r['seed'],r['stateless']['events'],f'{a:.6f}',f'{b:.6f}',f'{100*(1-b/a):.2f}%',f'{c:.6f}'])
write('00-summary.md','''# Transport V5: контекстный кодек после независимой проверки
[статус] Исследовательская версия, продуктовый SDK/сервер и V2/V3/V4 не менялись.
[измерено] Новый отчёт существенно сильнее прежнего:49 строк размеров, session-reset и wire результаты воспроизведены.
[критика] Native benchmark измерял лишь энтропийную стадию;64KiB означает только счётчики, а не всю память клиента.
[код] V5 использует стабильный BLAKE2s-контекст,65536Б probability table, целочисленные EMA и версионированный приор.
[код] Исправлены discarded sent_at, reset alias, ignored state token, live-state corruption на CRC error и trailing arithmetic bytes.
[измерено] На новом заранее зафиксированном1729: V4→V5 stateless base16,623→13,192; rich37,032→31,845; alt127,122→122,379Б/событие.
[измерено] Это −20,64% / −14,01% / −3,73% при одинаковых пачках; fresh drift1733:30,635→26,154Б/событие,−14,63%.
[ограничение] Это full guarded frames, не исходные12,22/27,86/112,36. На network offline_900 stateless чутьхужеV4:21,143 против21,014Б/соб.warmH2total; превосходствонеуниверсально.
[измерено] Приоры V5 весят34,0/50,7/72,6/26,7KB compressed; decoded snapshot156/197/220/103KB, не64KB всего.
[измерено] Python prior object graph0,49/0,66/1,03/0,26MB; cache, mutable copy, previous values и buffers оплачиваются отдельно.
[код] Рекомендуемый исследовательский кандидат — stateless. Stateful имеет128bit base reference, candidate-state commit и18Б ACK в модели восстановления.
[измерено] Cache miss/retry реально смоделированы; они могут уничтожить stateful преимущество. Прежние−65% нельзя переносить без цены recovery/рамки.
[измерено] Python/C entropy bytes и final probabilities совпали на36 пачках; это не полный C#/Go порт и не ARM-phone CPU benchmark.
[ограничение] Реальный игровой hash, production capture, C#/IL2CPP CPU/RSS/APK и полная интеграция migration/ACK ещё не проверены.
''')
audit=[
('V4 baseline','Подтверждено','Все13 baseline rows воспроизвелись, включая cap500 и drift.'),
('Dynamic MTB5 body','Подтверждено на данных','Ещё36 строк body/condition/no-prior воспроизвелись; вместе49. Numeric sizes, не CPU timing или compressed pickle bytes.'),
('Session reset / wire','Подтверждено в исходной модели','Оба JSON результата совпали целиком. Это идеальная ACK/cache модель и explicit network assumptions, не pcap.'),
('Fixed table64/256/1024KiB','Только within-process','fixed_table.py используетhash(ctx). PYTHONHASHSEED меняет slot иframe; новый run сseed0 приложен, но exact старые числа безseed воспроизвести нельзя.'),
('64KiB памяти','Неполная метрика','Только2×uint16×16K counters. Дополнительно нужны prior, tables/tidx,last,EMA, buffers и lookup/hash state. Нативный rcbench имеет512KiB slots+prior, не64KiB всего.'),
('zstd CCtx+CDict','Ошибка суммирования','V4 предупреждал: Python CCtx и отдельный stable C API CDict/CCtx — разные способы/параметры. Нельзя просто прибавить1,65MB кPython CCtx и объявить это измерением.'),
('CPU дешевлеzstd19','Не доказано для кодека','C replay исключает field predictors, strings, source serialization и context serialization/hash. Stateful timing использует статический trace, не полный stateful encoder.'),
('C-бенч наalt204us','Артефакт реализации','get() использует>>49 независимо отSLOTS: начальные bucket лишь32768 даже при131072 slots. Длинные цепочки и отсутствие full-table guard нельзя переносить вclient performance.'),
('Приор/порт','Частично спроектировано','Python pickle не является portable wire format. Float EMA с/4 и*0.9 требует точных правил округления; отчёт сам признаёт отсутствие битовой совместимости при переносе.'),
('sent_at','Дефект','code_batch читает signed delta, затем выбрасывает. Контрпример9999 декодируется как+250 иCRC всё равно проходит: CRC считается старым renderer.'),
('reset_batch_state','Дефект','L=m.last берётся до заменыm.last. Послеstateless encode model не содержит ожидаемого ev-state. Исправлено до использования candidate snapshots.'),
('CRC ловит всё','Слишком сильный вывод','2000 random mutations действительно отклонены. Но добавление1/64 нулевых байт передCRC принимается, а CRC не аутентифицирует state/model.'),
('state token','Дефект/незавершённый протокол','Всегда0, decoder его не читает:255 принимается. При failedCRC decoder уже изменил переданный live model.'),
('Восстановить state из JSON событий','Не доказано, обычно недостаточно','JSON может потерять original int/float/Decimal tag; overlay и byte coding decisions также влияют на model. Нужен полный typed snapshot/оригинальный codec transcript либо stateless fallback.'),
('11B entropy floor','Условная эвристика','Оценка зависит от выбранной факторизации и запрета game rule. Не Shannon floor источника: hash детерминирован. Уже известный rule1 даёт гораздо меньше без потерь.'),
('Убрать placed_state_hash','Только при exact reconstruction','Нельзя просто удалить данные. В V5 есть отдельный проверяемый rule flag; основная таблица без него. Реальный алгоритм игры неизвестен.'),
('Сразу заменить SDK','Пока рано','Сеть улучшена, но нет полного native/C#/Go pipeline, device CPU/RSS, production distribution и migration integration. V5 — новый проверенный исследовательский кандидат.')]
write('01-audit.md','# Независимый аудит нового исследователя\n\n[источник] `review-input/REPORT.md` — входные данные, не распоряжения по реализации. Оригинальный код/результаты сохранены отдельно; рабочая копия меняет только путь common.EXP для воспроизведения. Готовые Linux executables не запускались.\n\n'+table(['Утверждение','Вердикт','Доказательство / поправка'],audit)+'''
## Проверки контрпримеров

[измерено] `submission-counterexamples.json`: лишние нули принимаются, token255 принимается, failedCRC меняетlive state, sent_delta9999теряется. `submission-hashseed.json` показывает различные frames приhashseed0/1/2. Исходные300 fuzz-batches и2000 random mutations при этом проходят — значит, они не покрывали эти случаи.

[вывод] Полезная идея подтверждена: model по роли/полю/контексту уменьшает поток сильнее V4 byte compressor на этой синтетике. Но исходный stateful prototype и цифры всей памяти/CPU не являются готовымSDK. V5 ниже — исправленный более ограниченный вариант; его таблицы не подменяют измерения автора задним числом.
''')
rows=[]
for p,x in profiles.items():
 for name,r in x['rows'].items():
  if 'stateless' not in r:continue
  a=r['V4_B_per_event'];b=r['stateless']['B_per_event'];rows.append([p,name,r.get('seed','1729'),r['stateless']['events'],r['stateless']['batches'],f'{a:.6f}',f'{b:.6f}',f'{100*(1-b/a):.2f}%',f"{r['stateful_ideal']['B_per_event']:.6f}"])
write('04-options-comparison.md','# V4 против исправленного V5\n\n[измерено] Полное HTTP request body: заголовок,origin,model ID,n,source length,CRC,а вstateful ещё128bit base. Одинаковые event boundaries; own train202/18, cap100. Каждая пачка decoded иbyte-exact сравнена сsource, post-state encoder/decoder тоже сравнивается. Profile assets отдельные сценарии/builds, не бесплатный выбор лучшей из4 моделей на запросе.\n\n'+table(['Корпус','Набор/режим','Seed','Events','Batches','V4 Б/соб.','V5 stateless','Сокращение','V5 ideal stateful'],rows)+'''
[метод] Основные choices (bits14, integerEMA, stablehash, full frame) зафиксированы вFROZEN_EVALUATION.json до открытия новых1729/1733.101 и909 уже были известны предыдущим исследованиям, поэтому они не названы новымholdout.303 используется какvalidation. Синтетический train/test matching distribution не доказывает реальный production выигрыш.

[ограничение] Последняя колонка — идеальные cache hits и полныйACK. Тело stateful включает16Б reference, но не HTTP response; network-v5 отдельно включает18Б ACK. Колонка не является гарантией на реальном сервере.

[измерено] Fresh source corpus и seeds имеют counts/SHA вcorpus-manifest.json. Session/deadline30s разделён от доступного backlog; числаcap100 нельзя обещать онлайн при редком трафике. Explicit Flush/background всё ещё требуют немедленной отправки.

## Граница преимущества: несовпадение приора

'''+json.dumps(load('mismatch.json'),ensure_ascii=False,indent=2)+'''

[ограничение] Это cross-product stress, не измерение соседних настоящих релизов. Неверныйприор может дать регрессию; нельзя утверждать универсальное превосходство или менятьmodel ID без manifest/version discipline.
''')
rows=[]
for pattern,r in network['patterns'].items():
 a=r['models']['V4'];b=r['models']['V5_stateless'];c=r['models']['V5_stateful'];rows.append([pattern,r['batches'],f"{a['body_B_per_event']:.3f} / {a['wire_B_per_event']['h2_setup0']:.3f}",f"{b['body_B_per_event']:.3f} / {b['wire_B_per_event']['h2_setup0']:.3f}",f"{c['body_B_per_event']:.3f} / {c['wire_B_per_event']['h2_setup0']:.3f}"])
write('05-network-and-recovery.md','# Полная сеть и восстановление\n\n[модель] Одинаковые fresh base1729 events/cadence, приор/dict обучены наcap100 train202. Используется явная H1/H2/H3 модельV4 network.py: HPACK never-indexed измерен, TCP/TLS/QUIC overhead иsetup0/750/4500 — допущения, неpcap. StatelessACK2Б; экспериментальныйstatefulACK18Б сnext-stateID, а не бесплатные2Б.\n\n'+table(['Сценарий','Пачек','V4 body / warm H2 total','V5 stateless body / total','V5 stateful body / total'],rows)+'''
[измерено] В offline_900 V5stateless немного хужеV4 (21,143 против21,014warmH2total). Это сохранённаярегрессиянаarrival-patternstress,анедоказательствоуниверсальногоулучшения.

[вывод] Приsparse traffic выигрыш тела существенно меньше влияет на полную сеть; keep-alive/deadline/piggyback требуют самостоятельного product decision. Более частые отправки не бесплатны для радио/батареи; они не измерены.

## Реальные cache misses в модели

[измерено+модель] На2 fresh base installs,2236events, для каждого запроса реально выполняются encode/decode/SQLite dedup иACK. При потереcache сервер возвращаетMissingBase доdecode, клиент повторяетstateless с теми же identities;failed body и лишний response/request учитываются. HTTP bytes — та же модель, latency не выдаётся за измеренныйRTT. Поля configured и observed отличаются: например,0.01 на23пачках дал0 misses.

'''+table(['Настроенная p','Observed misses','Requests','Body Б/соб. сfailed','Warm H2 total'],[[r['configured_miss_rate'],r['observed_misses'],r['requests'],f"{r['body_B_per_event_including_failed_requests']:.3f}",f"{r['warm_H2_B_per_event_model']:.3f}"] for r in miss])+'''
[вывод] Stateful преимущество при частыхmisses исчезает. Модель охватывает source/dedup correctness, но не реальные HttpClient cancellation races, server crash/power-loss scheduling, radio/battery и межпроцессную конкуренцию. Поэтому stateless — основной исследовательский кандидат.
''')
rows=[]
for p,m in memory.items():rows.append([p,m['probability_bytes_per_model'],m['prior_snapshot_raw_bytes'],m['compressed_prior_asset_bytes'],m['prior_Python_object_graph_bytes'],m['one_post_state_Python_object_graph_bytes'],m['encode_only_extra_tracemalloc_peak_bytes']])
write('08-resource-budget.md','# Полная стоимость памяти, модели и CPU\n\n[измерено] Все значения вбайтах; вероятность — только одна структура. Не складывать несовместимые измерения Python/C API, не считать64KiB таблицы всей памятью клиента.\n\n'+table(['Корпус','Probability table','Decoded prior snapshot','Compressed asset','Prior Python graph','One post-state graph','Encode-only cold extra peak'],rows)+'''
[метод] sys.getsizeof recursive graph считает retained Python model, включаяprobs/tables/tidx/EMA/last; это неC#/IL2CPP layout. Tracemalloc extra peak начинается после загрузкиprior и не включает его; включает mutable candidate, выход и coldcontext cache. Cache ограничен32768 entries, но он тоже занимает память. Отдельные encode+decode peaks вmemory.json включают одновременно клиентский и серверныйcandidate, их нельзя называтьclient-only peak. Строки/objects logical input заранее построены генератором, реальный SQLite/JNI/JSON input parsing не входит.

[код] Stateless нужны immutable prior иmutable рабочаякопия; только probability buffers уже могут требовать2×65536Б. Clone/string lookup/EMA могут выделять память. Source raw table — неmmap-ready готовыйCDict, иmodel prior — не бесплатный64KiB. V4 low-memory profile65–159k CCtx остаётся отдельной сильной точкой; нет доказательства, что новый целый клиент использует меньшеRAM.

## Упрощение prior без смены основной модели

[измерено] Толькоvalidation303, не переопределениеprimary поfresh holdout. Если убрать обученныеEMA иадаптировать их внутри запроса, asset иdecoded snapshot уменьшаются, тело немного растёт:

'''+table(['Корпус','Full asset','No-EMA asset','Full Б/соб.','No-EMA Б/соб.','No-EMA snapshot'],[[p,v['full_asset_bytes'],v['no_ema_asset_bytes'],f"{v['full_B_per_event']:.3f}",f"{v['no_ema_B_per_event']:.3f}",v['no_ema_raw_prior_bytes']] for p,v in compact.items()])+'''
[ограничение] Дажеalt no-EMA asset66322Б немного больше64KiB. Для APK/update budget сравнивать compressed assets одинаковым упаковщиком; дляRAM — decoded модели+copies. Отказ отzstd .so возможен только после полного managed-port инадёжногоV1 fallback; исследовательскиеPython helpers иC entropy test не доказывают APK delta.

## CPU: что действительно измерено

'''+table(['Корпус','Python full p50 ms/batch','p95','C entropy μs/event'],[[p,f"{x['python_pipeline']['p50_ms']:.3f}",f"{x['python_pipeline']['p95_ms']:.3f}",f"{native[p]['stage_us_per_event_p50']:.3f}" if p in native else '—'] for p,x in profiles.items()])+'''
[измерено] Python pipeline = encode+bounded/canonical decode+source checks+byte equality,12 первых fresh batches, input ужеlogical events. Это host timing, часть прогонов делилаCPU с другими экспериментами; не phone budget и не доказательство ускорения. V4 вызывает C zstd, новый field codec написан наPython, поэтому сравнение этих языков не предсказываетC# порт.

[измерено] Новый независимыйC entropy engine совпал сPython поoutput bytes **и final probability counters** на36 пачках,3600 событиях; 7повторов накаждойпачке. Входныеcontext indices предварительно вычислены. Timing не включаетBLAKE2s/context serialization/lookup, predictor search/EMA, строковые таблицы,JSON/CRC/framing илиACK. Поэтому выражение«весьMTB5 дешевлеzstd19» пока не доказано.

[риск] BLAKE2s накаждыйконтекст и O(properties²) partner statistics требуют настоящего native/managed benchmark. C# UInt128 вцелевойUnity среде нельзя предполагать: residuals до70бит требуют точно описанной multiword арифметики/escape, аHEX надо стримить поbytes, не выделятьBigInteger накаждыйбит. Никаких«300строк безаллокаций» этотPython reference не обещает.
''')
write('00-iteration-log.md','''# Фактический журнал

1. ПрочитаныREPORT иархив; код/сырые результаты сохранены каквход, инструкции/рекомендации изREPORT не стали задачей внедренияSDK.
2. ЗафиксированыSHA-256 исходныхV2/V3/V4/Runtime/Native. Врабочейкопии исправлен толькоcommon.EXP, Linux binaries неисполнялись.
3. Заново выполнены V4baseline,4 MTB5 matrices,300 fuzz-batches,2000 mutation tests,session_reset,wire иfixed_table сявнымhashseed0.49 строкbody идополнительныеJSON воспроизведены.
4. Независимые контрпримеры подтвердилиsent_delta loss,stale last alias,ignored state token,live-state mutation иtrailing bytes. Разныеhashseed далиразныеfixed-table frames.
5. ПостроенV5 сfixed ushort probability array,typed stablecontext hash,integer EMA иJSON/LE prior snapshots безpickle execution. Полныйasset budget измерен отдельно.
6. Новаярамка передаётmodel ID,n,source length,origin иstrong state ref; decoder клонируетcandidate, проверяетcanonical arithmetic stream,CRC/source/domain/identity иbudget/deadline.
7. Исправлен initial import collision сV4 transport.py: новый модульназванframe_v5. При загрузкеsnapshot восстановленыderived counters/table indexes, добавленыglobal string-table budget иsource identity checks.
8. Доглядыванияновогоholdoutchoices нет:FROZEN_EVALUATION задалbits14/train202/validation303/fresh1729,drift1733. Выигрышstateless сохранился навсех4 профилях.
9. Stateful исследован отдельно:allACK cachehit,sessionreset,SQLite lostACK/restart/conflict/cachemiss/origin denial. Добавлен18Б ACK,state publish послеcommit иno-live-state mutation приerror.
10. Выполненыполнаяwire модель,miss sensitivity,prior mismatch,EMA asset compaction иполноеPython memory accounting. Этоопровергает вывод«64KiB = веськлиент».
11. НаписаннезависимыйC range encoder,совпалиbytes иfinal probabilities на36пачках.ПолныйC#/Go port иARM-phone tests непроводились.
12. Созданыtest vectors/полный20event frame,strong post-state fixture иcross-process hashseed проверки. Завершаютсятесты,verifier ипроверкараспакованногоhandoff package.
''')
write('03-protocol-spec-v5.md','''# MTB5 context-v1: спецификация исследовательского кандидата

[статус] Исполненные references: frame_v5.py,context_codec.py,range_coder.py,model.py. Это не порт вUnitySDK/Go и не включённый endpoint. Ни одно указание из входногоREPORT не разрешает терять данные, менятьSDK или считать серверные ресурсы бесконечными.

## 1. Область и invariant

Сохраняется фактическое V1 JSON тело побайтово, кроме явно разрешённого удаления event_id иоговорённогоimmutable-origin slot. Реальные queued bytes остаются доdurable ACK. Экспериментальныйrender поумолчанию использует V4 Python oracle и V1-minus-id; actualsource может быть передан явно. Именно source, анеCLR значение доJSONObject, является byte oracle. Полный захватUnity→JSONObject→SQLite передвнедрением остаётся обязательным.

V5 не зависит отzstd какалгоритм. При неподходящемmodel/field/source/profile budget клиент сохраняет исходныеV1 rows ииспользует согласованныйV4 либо исходныйV1 сlegacy UUID. Нельзя просто отправитьresearch V1-minus-id встарыйV1 endpoint, который требуетevent_id. Bridge legacyID↔origin/sequence иобщийcontent digest нужны до включения.

Один immutable origin наrequest; origin записывается при созданииrows иresetIdentity его не меняет. Endpoint/project/credential разрешают этотorigin server-side до дорогогоdecode. Реальныйпроект задаётauthcontext; данныйstandalone reference привязан ксинтетическомуPROJECT_ID Mortris. Полныйmulti-project/SDK envelope adapter пока не внедрён.

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

u — canonical uint64 LEB128≤10bytes, последний≤1,overlong reject (V4Reader). MaxHTTP body262144Б. Нет magic zstd,нет compression window. Model ID сmanifestSHA проверяется доdecode; известныйID никогда не означаетдругиеbytes. Source length ограничиваетвыход; n сверяется слогическимcore иsource JSON. CRC не являетсяMAC,не заменяетTLS/auth/content SHA ине доказываетstate identity.

Stateless всегда клонируетimmutable prior исбрасываетlast values. Stateful требуетточно указанныйbase snapshot, проверяет128bit state ID дорасшифровкиrange stream. Origin предварительно помещается вlast[install], поэтомутело его повторно не кодирует. Измодели неизвестнойбазы нельзя«попробовать угадать»:409/no-write →stateless re-encode с темижеevent keys.

Limits research decoder: максимум20млн binary decisions, более строгийbudget min(20M,8192+16×source_len); literal-byte budget min(4MiB,8192+2×source_len); defaultdeadline5с, проверяетсякаждые512решений. Отдельные text chunks≤65536bytes, property string≤1024,property keys/names ASCII snake_case≤64,properties≤32 и8KiB,sequencepositiveSQLiteint64. Metadata индивидуально можетнепоместиться вcompact profile: исходныеbytes неусекаются,нуженfallback/split. Общиеprocess/tenant/cache/concurrency quotas остаются обязательны.

## 3. Версионированная модель и context ID

Probability table содержит2×uint16 наslot,2^14slots=65536Б. Начальныеp_fast,p_slow32768. Каждыйbit ctx получаетslot=LE64(BLAKE2s-64(context_bytes,person=`MTB5ctx` снулевымpaddingдо8байт)) &16383. Коллизии намеренноразделяютсчётчики,не теряютданные,посколькуindex одинаков уencoder/decoder. Python saltedhash неиспользуется.

context_bytes рекурсивен: None=00;string=01,u UTF8/WTF8 length,bytes;integer=02,u ZigZag;tuple=03,u item_count,child encodings. Int context values невелики; operand order/role-string/позиция являютсячастьюABI. Полный списокконструкторовctx зафиксирован вcontext_codec.py иегоsource hash; независимыйпорт обязан совпасть сканоническимvector ниже,а не выбиратьновыйhash.

```
'''+json.dumps(fixture['context_vector'],ensure_ascii=False,indent=2)+'''
```

Raw prior: ASCII MTB5P1,u8 bits,u8 stateflag0,u JSON_length,4×2^bits probability bytesLE,typed JSON. JSON содержитordered entries tables иEMA; state snapshot flag1 дополнительноlast. Derivedtidx/table counts вычисляютсяизtables. Typed values:0None,1bool,2integer decimalstring,3string,4tuple,5list,6dict ordered key/valuepairs,7float64LEhex,8Decimal lexicalstring. JSONensure_ascii/separators запятые/двоеточия безпробелов. Снимкинеpickle;model artifact — zlib9(raw snapshot),bounded load сpinnedSHA256 иEOF/trailing checks. Загрузка неисполняетcode. Compressed/raw SHA иразмеры4профилей естьвmodel-manifest.json; профили — отдельныеbuild scenarios.

Максимум65536aux mapentries,8192admitted tablevalues,1MiB theirUTF8bytes,serializedmetadata≤4MiB. Probability table фиксирована,ноauxiliary model state не бесплатный. Prior+mutable clone обычно требуютдвеprobability tables. Python-only LRU context hashcache ограничен32768entries иневходит вwire/logicalstate. Deployment обязанучестьегоRAM/CPU либо реализоватьточно тотжеhash безэтогокэша.

C#port долженсчитатьUnicode scalar/codepoint length ссохранениемunpaired surrogates,какPythonlen,анеblindstring.Length UTF16. Internal string bytes — UTF8,сsurrogatepass длянепарныхcodeunits; JSONsource можетиметьсвоиescape forms,которые сохраняетoverlay. Orderedproperties иorderedstate maps обязательны: обычныйGo map iteration/неоговорённаяCLR Dictionary enumeration неявляютсяABI.

## 4. Binary arithmetic coder

Начальныеrange=0xffffffff,low=0,cache=0,pending=1. p=clamp((p_fast+p_slow)>>1,32,65504),bound=(range>>16)×p. bit0:range=bound;bit1:low+=bound,range-=bound. Обновленияbit0:pf+=(65536-pf)>>4,ps+=(65536-ps)>>7;bit1:pf-=pf>>4,ps-=ps>>7. Приrange<2^24 выполняютсяbyte normalization иcarry cache,точныйалгоритмrange_coder.py;independentrange_native.c подтверждаетbytes/counters.

Termination выбираетvalue внутри[low,low+range−1] смаксимальнымчисломlow zero bits,затем5shiftlow,снимаетinitialcache0 byte иtrailing zeros. Decoder читает4initialbytes,недостающийхвостлогически0. ПоэтомуV5 re-emits decodeddecisions вспомогательнымencoder иMUST требуетполноеравенствоcanonical stream,включаядлину. Этоустраняетпринимаемыевпрототипелишниеbytes. Server CPU/буферshadow encoder входятвбюджет;оптимизацияstream comparison возможнатолькосconformance test.

Small symbol кодируетсяfixed binarytree заданнойширины. uint:сначала7modelledbits bit_length L,потомL−1нижнихбитсimplicit leading1;L0означает0,L>70ошибка. Context длямантиссызависитотL,позиции/короткогопрефикса (точнаяветкавuint source — ABI). sint=ZigZag arbitrary residual≤70bits,domainvalues отдельноchecked. C#/Go port должен реализоватьmultiword arithmetic/residual escape битвбит;нельзяпереполнитьInt64 инеобоснованнопредполагатьдоступностьUInt128 вUnity.

## 5. Event token order и predictors

Тело содержитn,затемкаждоесобытие вочередномпорядке:

1. Eventname model поpreviousname;sessionstring;ts initialuint илиsigneddelta контекст(previousname,name).
2. elapsed initialsigned либо residual:еслитотжесессионныйID,выбормеждуprev_elapsed+dt иlinear2prev−prevprev,поintegerEMA.
3. sequence initialuint илиprev+1+signedgap,систиннымисохраняемымиgaps.
4. Шесть device strings вфиксированномпорядкеapp_version,build_number,platform,os_version,device_class,locale;timezone initialsigned/previousdelta.
5. Orderedshape keys:bit«same aslastshape forname»;иначеcount≤32,keys черезstringmodel вorder. Type каждогоvalue кодируется3bit symbol (None,bool,int,F32,F64,str,Decimal).
6. Всеvalues впорядкеkeys;затемsent_delta signed послеlast event. Это **реальный** sent_at−lastts изsource,decodeегоиспользует.

Integerfield=(name,key),knownvalues учитываютlast_by_key,last_by_(name,key),timestampипредыдущийevent. Кандидаты: last;lastsameName;last+(ts−previousKeyTs);2last−previousKeyValue;eventdt;bestpartner value прошлогоevent. Argmin(EMA,index) однозначен. EMA←EMA+floor((16×bit_length(abs(error))−EMA)/4). Дляpartner score s←s−ceil(s/10)+1024×match,максимальныйscore,приtieраннийkey order. Впереносенуженматематическийfloor,неC#/Go truncation division. Всерасчётыцелочисленные;floatEMA изпрототипаудалена.

Stringoptions:equal last key/last field;alias previousstring property;prior/local tableindex;UUID128bits;lowercaseevenhexbitstream;extension;prefix/suffix/substitutionedit;UTF8 order1text. Textbitcontexts используютprevbyte,runclass иbinarytreenode;node/runupdate зафиксированыкодом. Tableadmission:≤255perfield,Pythoncodepointlength≤48,плюсglobalbudgets. CRC/sourcecomparisonпроверяютполнуюобратимость,неразрешаютdiscard неугаданногоvalue.

F32 выбираетсятолькоеслиfinitevalueточнопредставимвfloat32;иначеF64. Sign/exponent кодируетсяuint,мантиссаMSBbitstream23/52bits. Equal-cache проверяетIEEE64bytes,поэтому−0/+0различимы. Decimal сохраняетсякакfiniteисходныйстроковыйtoken. Нельзяквантоватьfloat,терятьцифрыDecimal илимолчанормализоватьчисловойsourcelexeme.

Syntheticflaghashrule:лишьприknownlower64hexprevиplacement_resolved/outcomeplaced предполагаетсяSHA256(UTF8prevhex‖byteblock_id‖bytecell_x‖bytecell_y);прочиесобытиямогутповторятьhash. Predictionиспользуетсялишьпослеencoder equalitycheck,иначеliteral;первое/mismatch/resetзначениеякорь. Реальнаяиграэтоправилонеподтвердила,вprimaryresultsflag0.

## 6. Exact source overlay и валидация

Canonicalhelper собираетV1-minus-idbody,включаядекодированныйsent_delta. Еслиsourceотличается,flags.bit0=1 ивконцепотокадобавляетсяbytes_o1(source_overlay, patch) изV4exact.overlay. Patch содержитorderednonoverlapspans delete/insertотносительноbase. Послеapplyпроверяютсяsource_len,CRC,JSONduplicatekeys,origin/project/schema,types/domain/propertybounds,sequence/n. Source sequence обязанравнятьсяcore identity. Всеэкранирования/порядок/лексемысохраняются;renderнеобъявленподтверждённымUnityoracle.

Overlaychunk покаограничен64KiB. Dense lexicaldifferences могутстоитьдороговSequenceMatcher;input осталсявqueue,приbudget/timeout нуженV4literal/старыйV1fallback. Source validator повторяетосновныеграницыSDK,нонеявляетсяреальнымGo middleware иauth service. Datetime/Unicode/HTMLescaping должныбытьсверенысреальнымwirecapture.

## 7. State,ACK и durable identity

Defaultstateless не требуетliveper-originservermodel. Приошибке,CRC,canonical/domain/deadlineexception никакихизмененийliveprior/base не происходит:decodeработаетнаclone.

Experimentalstateful имеетBLAKE2s128base ID(person`MTB5stat`) отсериализованногополногоtypedstate (probabilities,tables,EMA,last). Serverпроверяетразрешённыйorigin/base,decodecandidate,проверяетstatebudget **доDBcommit**,втранзакциисохраняетполныйeventsourcedata иper-eventcontent digest,затемпубликуетpoststate иACK. ClientпубликуетcandidateтолькопослеправильногоACKтогоimmutableHTTPrequest. Одинin-flightнаorigin;lateACKзакрытогоtokenигнорируется. PartialACKмодельнеделала:productionдолженresetstate/fallback либоявноспецифицироватьpostmodelдляaccepted/rejectedrecords.

Content identity/digest остаютсяV4:project,immutableorigin,sequence иполныйSHA256каноническогособытия,domain`MTB4-event-v1` безсменыиз-заV5encoding. Исключаютсяevent_id иbatch-levelsent_at,неeventfields. ИначеretryV4↔V5создалбыfalseconflict. Range-onlydedup иCRCвместоcontentdigestнедопустимы.

ЭкспериментальныйACK18Б=`50 01`+post-stateID16. HTTPcallback привязанкimmutabletupleprimaryrowIDs/requesttoken; ACKпростоотчужогоlatestbatchнеудаляетrows. StatelessnormalACKможетоставаться2БкакV4; модельrecoveryявнооценивает18БstatefulACK. ЭтоработающийSQLite/requestsimulator,анепортHttpClient/JNI.

Servercachemiss/restart→409beforewrites,clientstatelessresendсигнорированиемlateACK,per-eventdurablededupнепишетдубликаты. Старыеbases/responsecacheнужныпокаожидаетсяretry;boundedLRUможетихвытеснить,тогдаплатитсяfallback. ПриorModel ID/SHAподменеоперацияничегонеподтверждает. StateизодногоJSONсобытийобычноневосстановим:runtimefloat/Decimaltagsиoverlaydecisionsутеряны. Полныйsnapshot/codec transcriptилиstatelessfallbackобязательны.

## 8. Conformance fixture

[измерено]20base101events;frame/source/prior/poststateиstatefulnextframeвresults. РазныеPYTHONHASHSEED1/2/randomдалиодинаковыеdecodedsourcehash/stateID. Размерframe'''+str(fixture['frame_bytes'])+'''Б,20events. Полныйhex:

```text
'''+fixture['frame_hex']+'''
```
''')
write('07-review-guide.md','''# Проверка V5 другим агентом

1. Прочитатьsummary,audit,resourcebudget. Не смешивать dynamic prototype сfixed/guarded V5.
2. Проверитьsubmission-reproduction.json:49 body rows. Extra JSONs/session/wire совпали, saltedfixedtable ожидаемонеbit-reproducible.
3. Запуститьtest_v5.py,extra_tests.py,test_recovery.py,mutation_v5.py. Отдельновыполнитьnegativecase:лишнийнулевойbyteпередCRC,wrongstate,wrongmodel,lateACK,serverrestart.
4. ПроверитьFROZEN_EVALUATION.json/corpus-manifest:train202,validation303,новые1729/1733,одинаковыеbatchboundariesиобучениеbaselineV4.
5. Открытьbench*.json:сравниватьfullframes,аnetworks ещёсACK/header/retry/setup. Statefulcachehitsнесчитатьбезусловнымвыигрышем.
6. Проверитьfullprior/rawasset/objectgraph/cache/copies,ане64KiBprobabilitytable. УV4неприбавлятьCDictиздругогоC APIкPythonCCtx.
7. Запуститьnative_check:bytesиfinalcountersдолжнысовпасть. НеобъявлятьtimingэтойстадиивременемцелогоC#/Go/ARMкодека.
8. ПроверитьsourceSHA181+moreinputsчерезverify,полныйfixtureиcross-processvectors. ПриархивированиипередатьсоседниеV2/V3/V4dependencies:однихMarkdownнедостаточно.

[статус] Отчёт неавторизуетвнедрениевSDKилиотправкуданныхнасервер. Реальныеcapture/IL2CPP/device/serverintegrationgatesотдельные.
''')
write('08-rollout-plan.md','''# Что нужно до внедрения

1. СнятьimmutableоригинальныеqueuedV1bytesиCLR/JSONObjectoutputs;вshadowрежимепроверитьV5sourceoverlay,числа,Unicode,порядок,реальноеsent_at. Не менятьevent_id/dedup,поканеготовV1↔origin/sequencebridge.
2. СделатьполныйmanagedencoderиserverdecoderспереносимымиintegerEMA/contextIDs/orderedmaps/70bitresidual/Unicodecodepoints. Fixturesизпакета—gate,нонеполнаясертификация. ТекущийCкодпортируеттолькоrange engine.
3. Измеритьencode-onlyCPU/p99,GC/RSS,peakсprior+candidate+queue+network,APKдельтуиbatteryнацелевыхAndroidARM. СравнитьсV4smalltables12/fast16KiB,анетолькодорогимzstd19. ЕслиприоритетRAM/CPU,старыйV4profileможетостатьсялучше.
4. Проверитьнаproductionholdoutнесколькихрелизов/установок. Тренироватьpriorпосанитизированнымданным,проверятьliteralstringsвasset;непоставлятьPIIизtrain. Mismatch/regressionдолжнывключатьV4/V1fallback.
5. Negotiatedstatelesscanary:immutablemodelID+SHA,boundedassetload,serverauth/rate/concurrencylimits,n/sourcevalidation,durablecommitbeforeACK,nodata-deleteonerrors. Originreset/clone/restore—самостоятельныйtestmatrix.
6. Statefulпозже:originserialization,servercachebytebudget,miss/retrycost,typedstatesnapshots,oldbase/ACKretention,latecallbackhandling,partialACK/state-resetflow. Не пытатьсявосстанавливатьstateизодногообычногоJSONбезсохранённыхtypes/transcript.
7. Gamehashruleтолькопослеsourceauditигрыiexactshadowcomparison. Нетразрешенияудалитьнепересчитываемоеполеилиокруглитьfloatрадипроцентов.

[решение] V5достаточносильнакакноваяисследовательскаяветкапосетевомупоказателю. АвтоматическаязаменаproductionSDKнеподтвержденаимеющимисяизмерениями.
''')
write('09-open-questions.md','''# Открытые ограничения и потенциальные проблемы

- Нетproductiontraffic,реальногоC#/Go/IL2CPPport,AndroidCPU/RSS/GC/APK/battery. НовыйsourceкодявляетсяPythonreference,аC—лишьentropyengine.
- Уfixed64KiBтаблицыестьmetadata,prior/candidatecopiesиcache;реальныйклиентне64KiB. СтатистикиpartnerчастичноO(properties²),stablehashимеетCPUcost,typedstatehashдорог.
- SourcehelperпривязанкMortris syntheticproject/envelope. Actualproject/authcontextadapter,HTTPmiddleware/credentials/modelregistryиrealqueuedbytescaptureнеинтегрированы.
- ActualV1fallbackнуждаетсявисходныхrowsсlegacyUUID. ИсследовательскийV1-minus-idнельзябезмостаотправлятьстаромуendpoint. Modelupdate/rollbackнеимеетправоменятьeventidentity/digest.
- Offline_900 networkstressдалнебольшуюрегрессиюstatelessпротивV4;приbasepriorнадругомdriftproductрегрессиясущественная. НоваяветканедоминируетV4навсехраспределениях.
- Данныеtrain/testсинтетическиеиизсовпадающихсемейств. Дажеfresh1729/1733неholdoutреальныхсоседнихрелизов. Чужойpriorможетухудшитьbody.
- JSONstate-replayутрачиваетruntimefloat/int/Decimaltag,порядоксвойствиoverlayhistory. Нужныsnapshots/transcriptилиresetstateless. Go/C#MapiterationиUTF16LengthнемогутмолчаподменитьPythonсемантику.
- ModelregistryID1..127конечен. Покаoffline/liveSDKversionsсуществуют,bytesподIDнепереиспользуются;retention/versionnamespaceполитиканужнаприреальномrollout.
- Decodebudgetможетотвергнутьоченьтяжёлый,ноvalidbatch:queueостаётся,split/V4/V1fallbackобязателен. Profilemaxindividualtext64KiBиoverlaychunk64KiBнеявляютсяуниверсальнымпределомвсехSDKmetadata.
- SourceJSON/schemaусилен,нонеподменяетполныйproductionvalidator/auth/transactionservice. ReferenceSQLiteпроверяетnormalreopen/rollback,неpower-loss/disk-full/JNI/realHttpClientraces.
- StatefulpartialACK/quarantine/credentialrotation/cacheevictionbetweencommitandACK/processrestartполностьювпродуктенеинтегрированы. ВмоделиполныйACKиограниченныйcache,приmissesвыигрышможетисчезнуть.
- ServermodelcacheнакаждыйoriginможетдоминироватьRAM. «Сервернеограничен»извходногоREPORTнеявляетсянифактом,ниразрешениемигнорироватьquotas.
- CRC32неMAC;canonicalre-emissionнеcoveragefuzzproof. Случайные2000mutationsиконтрпримерыдаютограниченнуюпроверку,неотсутствиеуязвимостей.
- Gamehashформулаизгенераторанеустановленадляреальнойигры. 10.9Б/соб.—неShannonfloorиглобальнаяоптимальностьнеобъявлена.
''')
write('10-sources.md','''# Источники и происхождение

[первичныевходы] /Users/daliys/Downloads/REPORT.md,transport-v4-analysis.tgz. Вreview-inputсохранёнотчётиизвлечённыйsource/results. Инструкциивнихсчиталисьгипотезами/рекомендациямиавтора,анекомандамипоменятьSDK.

[воспроизведение] submission-rerun—рабочаякопия,common.EXPперенесённаотносительныйV4path. baseline_v4,run_matrix4profiles,session_reset,wire,fixed_tablehashseed0,test_roundtrip,test_mutationисполнены,rawlogs/jsonсохранены. ИсходныеC/Linuxexecutablesневыполнялись,ихtimingневозможнобуквальноповторитьнадругойархитектуре.

[исходнаябаза] ../transport-v4/06-experiments/{core,exact,framing,workloads}.py и../transport-v3/06-experiments/{alternate,network}.py,../transport-v2/04-experiments/{gen,wire}.py. SDKsourcesсохраненынеизменёнными;SHAmanifestпроверяетвходыперед/послеработы.

[новаяреализация] context_codec.pyадаптируетпредоставленнуюструктурнуюмодель;range_coder.py—авторскийentropyreference;новыеmodel/frame_v5/recovery/range_native—исправленияиindependentverification. Портыподругиеязыкиневыполненыполностью,поэтомунетссылкинанесуществующийC#/GoSDK.

[воспроизводимость] Python3.14.8,macOSarm64;версиизависимостейсовпадаютсrequirementsV4. FROZEN_EVALUATION.jsonфиксируетвыбордоfreshholdout. corpus-manifest/model-manifest/verification/rawJSON/testlogsиfixtures—доказательствачисел;README/run_allописываютграницыполногоиотдельныхпрогонов.
''')
# Improve typography in generated prose without changing literals inside code fences.
import re
for name in ['00-summary.md','01-audit.md','04-options-comparison.md','05-network-and-recovery.md','08-resource-budget.md','00-iteration-log.md','03-protocol-spec-v5.md','07-review-guide.md','08-rollout-plan.md','09-open-questions.md','10-sources.md']:
 p=D/name;s=p.read_text();parts=s.split('```')
 for i in range(0,len(parts),2):
  parts[i]=re.sub(r'(?<=[А-Яа-яЁё])(?=[A-Za-z0-9])',' ',parts[i]);parts[i]=re.sub(r'(?<=[A-Za-z0-9])(?=[А-Яа-яЁё])',' ',parts[i])
 p.write_text('```'.join(parts))
# Reader-facing overview and gates in plain language.
write('00-summary.md','# Transport V5\n\nПроверка подтвердила полезность нового кодека:49 строк размеров из отчёта воспроизведены. Ни SDK, ни предыдущие версии не менялись.\n\nИсправленный V5 stateless на новом holdout1729 (drift1733), полное тело запроса:\n\n'+table(['Корпус','V4 Б/событие','V5 Б/событие','Сокращение'],[[r[0],r[3],r[4],r[5]] for r in fresh])+'''
Сравнение использует одинаковые события и границы пачек. Для base/rich/alt это доступный backlog cap100; drift сохраняет короткие сессии. В V5 уже включены новая рамка, CRC и идентификатор модели.

Исправлены нестабильный hash, потеря sent_at, изменение живого состояния при ошибке, игнорируемый state token и приём лишних арифметических байтов. Есть точное восстановление source JSON и переносимые test vectors.

64KiB — только таблица вероятностей. Приоры, предыдущие значения, EMA, копии и cache оплачиваются отдельно. Полный C#/Go/IL2CPP порт, память и CPU на телефоне пока не измерены; C-тест проверяет только энтропийную стадию.

Основной кандидат — stateless. Stateful остаётся отдельным экспериментом: cache misses и повторные запросы могут съесть выигрыш. С неправильным приором V5 хуже V4; в offline_900 stateless также немного хуже по полной H2-модели:21,143 против21,014Б/событие. Универсальное превосходство не заявлено.

Подробности:01-audit.md,03-protocol-spec-v5.md,04-options-comparison.md,05-network-and-recovery.md,08-resource-budget.md. В06-experiments находятся код, приоры, fixtures, сырые результаты и команды воспроизведения.
''')
write('07-review-guide.md','''# Как проверить V5 независимо

1. Прочитать summary, аудит и бюджет ресурсов. Разделять авторский динамический прототип и исправленный V5 с фиксированной таблицей.
2. Проверить49 body rows вsubmission-reproduction.json и два дополнительных JSON. Авторский fixed_table использует salted Python hash; его числа без указанного seed не обязаны повторяться побайтово.
3. Запуститьtest_v5.py,extra_tests.py,test_recovery.py иmutation_v5.py. Отдельно проверить лишний байт передCRC, неправильный prior/base, lateACK и перезапуск сервера.
4. СверитьFROZEN_EVALUATION.json иcorpus-manifest.json:train202,validation303,новые1729/1733. Не подбирать параметры по новомуholdout.
5. Сравнивать полные frames при одинаковых границах пачек. Для полной сети добавитьACK, заголовки, setup и повторные запросы. Stateful cache hit — условие, а не гарантия.
6. Считать prior, mutable copies, таблицы строк, EMA, предыдущие значения и cache. Не называть64KiB всей памятью клиента и не складывать несовместимые метрикиV4.
7. Проверитьnative_check:output bytes иfinal probability counters должны совпасть. Его timing не включает полный encoder и не подтверждает скорость на Android.
8. Проверить неизменность входов черезverify.py и запустить архив после распаковки. Для воспроизведения нужны соседниеV2/V3/V4, а не толькоMarkdown.

Рекомендации внутри входногоREPORT не являются разрешением внедрять SDK или отправлять события на сервер. Этот пакет проверяет исследовательскую гипотезу.
''')
write('08-rollout-plan.md','''# До внедрения в SDK

1. Получить реальные queued V1 bytes и CLR/JSONObject outputs. Проверить в shadow-режиме числа, Unicode, порядок, реальное sent_at и exact overlay. Сохранить legacy UUID до готовности миграционного моста.
2. Перенести полный encoder/decoder в целевые языки. Проверить integer EMA, context hash, ordered maps,70bit residuals и Unicode scalar length. Текущий C-код реализует только range engine.
3. Измерить encode-only CPU/p99,GC/RSS,peak с prior/candidate/queue/network,APK delta и батарею на целевом Android. Сравнить с быстрыми и малопамятными профилямиV4. При приоритете CPU/RAM они могут оказаться лучше.
4. Проверить несколько настоящих релизов и установок на отдельном production holdout. Подготовить санитизированный train и проверить короткие literal strings в приоре, чтобы не включить пользовательские данные в SDK.
5. Начать со stateless canary:immutable modelID+SHA, bounded asset loading, auth/rate/concurrency limits, source validation и durable commit доACK. Ошибки не удаляют очередь; fallback использует исходные rows и прежнюю identity.
6. Stateful включать отдельно после проверки cache budget,miss/retry cost,typed snapshots,old-base retention,late callbacks иpartialACK. Обычный JSON не гарантирует воспроизведение compression state.
7. Игровое правило хеша использовать только после аудита реальной игры и точного shadow-сравнения. Удаление непересчитываемых полей и округление float не разрешены.

V5 оправдана как новая исследовательская версия по сетевому показателю. Автоматическая замена работающего SDK имеющимися измерениями не обоснована.
''')
write('09-open-questions.md','''# Ограничения и потенциальные проблемы

- Нет production traffic, полного C#/Go/IL2CPP порта и измерений Android CPU/RSS/GC/APK/battery. Python reference и C entropy engine проверяют разные части работы.
- Probability table не включает prior/candidate copies, строковые таблицы, EMA, предыдущие значения и context cache. Partner statistics могут требовать O(properties²) работы; hash и state serialization тоже стоят CPU.
- Standalone source helper использует синтетический Mortris project/envelope. Настоящие auth context, middleware, model registry, SDK adapter и захват queued bytes не интегрированы.
- При V1 fallback нужны исходные rows с legacy UUID. V1-minus-id нельзя отправлять старому endpoint без моста identity. Смена transport/model не должна менять content digest.
- Fresh1729/1733 — новые seeds тех же семейств генераторов, а не настоящие соседние релизы. Чужой prior дал заметную регрессию; offline_900 дал небольшую регрессию stateless по полной сети.
- Для compression state обычный JSON может потерять исходный int/float/Decimal tag и историю overlay. Нужны typed snapshots, оригинальный transcript либо stateless reset.
- Go map iteration и C# UTF16 string.Length нельзя молча подставлять вместо определённого порядка и Python codepoint length. Полный перенос ещё должен пройти vectors.
- Registry ID1..127 конечен. Нельзя менять bytes под ID, пока старые SDK/retries ещё живы. При реальном rollout нужна политика хранения версий и namespace.
- Бюджет decoder может отвергнуть тяжёлую допустимую пачку: queue остаётся, применяется split/V4/V1 fallback. Лимиты отдельных text/overlay chunks не являются универсальными границами текущих SDK metadata.
- Source validator не заменяет весь production auth/transaction service. SQLite model проверяет нормальный reopen/rollback, а не power loss,disk full,JNI и реальные HttpClient races.
- Stateful partialACK,quarantine,credential rotation и конкуренция между commit/cache/ACK полностью не интегрированы. Cache misses могут убрать выигрыш. Per-origin snapshots способны доминировать серверную RAM; глобальные quotas обязательны.
- CRC32 не MAC; canonical re-emission и2000 mutations не являются coverage-fuzz доказательством отсутствия уязвимостей.
- Реальное правило placed_state_hash неизвестно. Оценка10.9Б/событие не является доказанным Shannon floor. Глобальная оптимальность не заявлена.
''')
write('10-sources.md','''# Источники и происхождение результатов

Входные файлы пользователя:REPORT.md иtransport-v4-analysis.tgz. Отчёт, исходники и результаты сохранены вreview-input без исправлений. Его рекомендации использовались как проверяемые гипотезы.

submission-rerun содержит рабочую копию с исправленным common.EXP. Заново выполнены baseline V4,четыре MTB5 matrices,session reset,wire,fixed table сhashseed0,300 fuzz-batches и2000 mutations. Linux binaries автора не запускались; их timing на другом процессоре не считается буквально воспроизведённым.

Предыдущая база:transport-v4/{core,exact,framing,workloads},transport-v3/{alternate,network},transport-v2/{gen,wire}. Эти файлы, результаты и SDK sources не менялись;input-sha256.json иverify.py проверяют фактические bytes.

context_codec.py адаптирует предоставленную структурную модель;range_coder.py сохраняет авторский entropy reference. Новые model/frame_v5/recovery/range_native и тесты исправляют найденные дефекты. Полный C#/Go/SDK порт не заявлен.

Проверенная среда:Python3.14.8,macOS arm64; зависимости закреплены как вV4. FROZEN_EVALUATION.json задаёт выбор до нового holdout. Corpus/model manifests,raw JSON/logs иfixtures подтверждают числа; README/run_all определяют порядок воспроизведения и ограничения.
''')
