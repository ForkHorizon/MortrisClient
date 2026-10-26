"""Render V4 documents from measured artifacts; no estimates masquerade as results."""
import json
from pathlib import Path
R=Path(__file__).resolve().parent;D=R.parent
load=lambda n:json.loads((R/'results'/n).read_text())
m=load('paired-matrix.json')['profiles'];h=load('holdout-resources.json');x=load('extreme-v4.json');q=load('queue-storage.json');nb=load('native-build.json');f=load('fuzz.json');ex=load('example.json');nm=load('native-memory.json')
def write(n,s):(D/n).write_text(s.strip()+'\n')
def table(head,rows):return '| '+' | '.join(head)+' |\n|'+'|'.join(['---']*len(head))+'|\n'+'\n'.join('| '+' | '.join(map(str,row))+' |' for row in rows)+'\n'
write('00-summary.md',f'''
# Transport V4: проверенный пересмотр
[измерено] Это исследовательская версия; SDK, сервер и материалы V2/V3 не менялись.
[измерено] Ответ внешнего агента сохранён; его итоговые V4 числа не воспроизводятся приложенными двумя скриптами.
[измерено] Полный свежий V2 run_all завершён, 12 детерминированных артефактов совпали побайтово; V3 снова прошёл 8233 события.
[измерено] Реализованы полный MTB4 encode/decode, FoR/BitPack/Elias–Fano, decimal scaling, XOR с отсечением нулей, локальные индексы и бинарный хвост.
[измерено] При cap100/dict64/level19 V3 → V4: base 17,051 → 16,621; rich 38,084 → 36,966; alt 129,506 → 126,605 Б/событие.
[измерено] Это −2,52% / −2,93% / −2,24%, без обещанных агентом −15–17%; словари каждого формата обучены на одинаковом бюджете.
[измерено] На новом holdout909 V3 → V4: 17,147 → 16,681 / 38,243 → 37,197 / 128,694 → 127,217 Б/событие.
[измерено] На независимом drift808 коротких сессий V4 хуже: 30,321 против 29,628 Б/событие; универсальное превосходство не доказано.
[измерено] Малые match tables дают CCtx 122693/158871/310124 байта вместо 2,39/2,51/5,14 МБ, ценой примерно +10–11% тела к V4 level19.
[измерено] Compressor-only Android arm64: 276832 Б; fast-only 116208 Б; это пробные NDK-сборки, не размер готового SDK/APK.
[измерено] Внешний код теряет -0.00, игнорирует session/device в digest, принимает усечённый zlib и выделяет ~7,6 МБ при заявленных 10 Б.
[код] ACK остаётся связанным с immutable request rows; 16-битный хеш не заменяет привязку; per-event cold digest сохраняется при ребатчинге.
[измерено] Проверены 6000 мутаций рамки/ядра, границы чисел/Unicode, точный lexical overlay и SQLite-модели retry/ACK/conflict.
[ограничение] Android runtime, battery, production corpus, Unity/JSONObject byte oracle и миграция очереди требуют отдельных проверок до внедрения.
''')
audit_rows=[
('Headline / D1','Частично верно','V3 явно разложил cadence/dictionary/frame в абляции и ограничил cap100 backlog/SLO. Новый формат действительно почти не даёт выигрыша сам по себе; заголовок стоит читать как конфигурацию, не формат.'),
('C1','Теперь подтверждено','Свежий V2 run_all в v2-rerun; 12 SHA-256 равны; сырой вывод приложен.'),
('C2','Подтверждено','DBL_MAX, lexical CTXREF и 70-bit varint остаются известными дефектами V2; V3 guard их обходит.'),
('C3','Подтверждено в синтетике','Alt является независимым генератором, не реальным релизным holdout; opaque160 сам по себе не делает корпус нечестным.'),
('C4','Полезная оговорка','rebatch100 — backlog upper benchmark. V3 это оговорил; V4 отдельно измеряет session/deadline30s и не обещает эти числа онлайн.'),
('C5','Арифметика верна','Весь основной выигрыш прежней cadence объяснён словарём. V4 даёт парную матрицу с равными dict16/64.'),
('C6','Нельзя обобщать','На alt target training почти ничего не даёт; теперь выбор сделан на validation303 и проверен на909.'),
('C7/C8 / D5','Гипотеза подтверждена частично','V3 якорь уже HEX32, не ASCII64: sentinel создаёт отдельный STR type, но HEX-якорь остаётся бинарным. Bitmap уменьшает неоднородность; полный кадр не всегда меньше.'),
('C9 / D4','Верная критика границы вывода','XOR-varint слабый proxy, bitpack/EF в V3 были stage estimates, не доказательство класса. В V4 они интегрированы и измерены после zstd; EF иногда ухудшает кадр.'),
('C10','Подтверждено ограничение','История4 на2 установках не доказывает универсальное преимущество/недостаток; в новую рекомендацию без recovery budget не включена.'),
('C11/C12','Риск есть, формулировка неверна','V3 уже ограничивает raw/window до2MiB и требует auth/rate limits. Это bounded amplification, не неограниченный alloc. n снаружи помогает, но n=500 можно подделать. Decodable mutations под TLS не означают нарушение целостности канала.'),
('C13','Опровержение агента не доказано','V3 прямо требует immutable request row binding. HTTP stream не назначает чужой ответ другой пачке. Ошибка клиента опасна; MAC16 её не устраняет. SQLite-модель проверяет timeout/late/reordered callbacks.'),
('C14','Нужна конкретизация, не заявленный контрпример','V3 уже требует канонизацию отдельно от framing и byte-exact fallback. Kind1 с отличающимися байтами по контракту запрещён. В V4 дана конкретная полная canonical-event схема; внешний digest дефектен.'),
('C15','Критика неполная','Финальные V3 проходы содержали linear/per-type, а не только флаги. Два <2% прохода — локальная остановка, не доказательство глобального оптимума. В V4 сделаны структурные опыты до финальных флагов.'),
('D2','Реальное направление','Удалены directory/kind0/dt0. Сырая экономия не равна сетевой, измерены целые кадры.'),
('D3','Реальное направление, числа не доказаны','Внешний код не реализует token/event escape. V4 использует точный byte overlay и literal fallback; это другой алгоритм с измеренной ценой, не ALP/Chimp.'),
('D6','Возможная оптимизация, отсутствует в коде агента','Внешний pack оставляет FHD/window bytes. Отдельный V4 trial реально убирает2 байта, синтезируя окно1MiB; в рекомендуемом framing стандартный header оставлен ради простоты/малых окон.'),
('V4 RAM/CPU/SDK/queue tables','Не подтверждены ответом','Никакого полного bench, профиля аллокаций, NDK artifact или queue migration в двух скриптах нет. Новые измерения приведены отдельно; оценки не складывались.'),
('V4 canonical hash / ACK','Неприемлемо как исправление','Digest исключает session/device, зависит от порядка; unkeyed BLAKE2s16 не MAC и игнорирует sequence gaps/content. [1,2,5] и [1,3,5] дают одинаковый input ACK.'),
('V4 диапазоны dedup','Нельзя заменить по-событийную проверку','Batch hash не позволяет проверить изменившийся subset/overlap при ребатчинге. Hot watermarks допустимы только поверх сохранённой durable per-event identity/content evidence.')]
write('01-audit.md','# Аудит ответа другого агента и V3\n\n[источник] Полный вход: `review-input/external-review.md`; оба code fences извлечены без исправлений.\n\n'+table(['Утверждение','Вердикт','Основание'],audit_rows)+'''
## Исполненные контрпримеры внешнему коду

[измерено] `external_audit.py` сначала запускает исходный self-test: exit0. Он проверяет только заголовок из10 hardcoded bytes, шесть числовых лексем, одну forged length и две integer-колонки. Не декодирует полный fixture472Б, не делает V3/V4 bench и не кодирует события drift.

[измерено] Дополнительные случаи: `-0.00 → 0.00`, `-0.000 → 0.000`; изменение session_id/device_class не меняет digest; перестановка свойств меняет digest. INT64_MIN→INT64_MAX вызывает переполнение разности, uint64.max не кодируется, empty encoder оставляет непрочитанный байт. Заявленные Chimp128, Elias–Fano, rANS, XDelta, схемные дельты, RAW_LEXEME и row/chunk queue codec отсутствуют.

[измерено] `zlib.decompress(..., raw_len+1)` затем безлимитный `flush()` распаковывает остаток бомбы до проверки длины: Python tracemalloc peak около7,6МБ. Поток без последних4байт checksum принимается: нет проверки eof. Новый `framing.py` не вызывает flush, проверяет eof/unused/unconsumed и preflight zstd параметры.

[код] Формула4096+n×8704 не выводится из текущего SDK: AppVersion/BuildNumber в AnalyticsDeviceContext не имеют такого ограничения. В4 это negotiated compact profile; превышение обязано сохранить source и перейти на прежний V1, не обрезать строки. Даже n=500 не снимает общий budget конкурентных запросов.

[измерено] Новый дефект генератора: session_start может иметь elapsed=-1 из random drift. Исторические сравнения сохраняют исходный корпус, не чинят его ради красивых чисел. Это ещё одна причина не считать синтетику реальным SDK oracle.
''')
rows=[]
for p,v in m.items():
 for cap in ['original','100','500']:
  for size in [16384,65536]:
   for model in ['V2','V3','clean','packed']:
    a=v[f'{cap}/{size}/{model}'];rows.append([p,cap,size,model,f"{a['B_per_event']:.6f}",f"{a['raw_B_per_event']:.3f}",a['events'],a['batches']])
write('04-options-comparison.md','# Парная матрица V2 / V3 / V4\n\n[измерено] Все числа — полное тело запроса, включая outer envelope и raw trailer. Для каждого формата отдельный собственный словарь того же размера, тот же train202/18 установок, test101/6. Словари заранее установлены: цена загрузки не включена в событие. cap100/500 здесь backlog без deadline, не поведение онлайн. V2 prefix2Б, V3/V4 — их реальные рамки. V4 frame дороже заголовком n/trailer, что включено.\n\n'+table(['Корпус','Пачки','Dict Б','Модель','Б/соб.','Raw Б/соб.','Событий','Пачек'],rows)+'''
[код] clean удаляет directory/CAS-kind/dt0, сохраняет bool bitmap, но использует обычные varint-потоки и binary floats. packed добавляет FoR/EF, scaled decimal/XOR, local indices и separated string lengths. trailer — packed с UUID/HEX tables вне zstd. Системные origin/session UUID и hash-predictor anchors пока внутри структуры; нельзя заявлять вынос всей случайной информации.

[измерено] Перебор этих вариантов на101 — исследование, не финальная оценка. Все три validation303 выбрали trailer; глобальный выбор минимизирует средний log-relative size с равными весами профилей. seed909 и drift808 использованы после фиксации выбора. Отдельно `holdout-resources.json` сравнивает уровни1/3/6/9/15/19 и малые match tables у V3 и V4 на тех же границах.

[ограничение] Настоящие Chimp128/ALP paper codec, FSST, полноценный rANS/context mixing и board-aware XDelta не реализованы этим пакетом. Они не объявлены проигравшими классами. Строки NUMTEXT сохранены для Decimal/экзотических числовых лексем; простое их удаление было бы потерей данных.
''')
rows=[]
for p,v in m.items():
 prev=None
 for label in ['V2','V3','clean','packed','noef','trailer']:
  a=v[f'100/65536/{label}']['B_per_event'];rows.append([p,label,f'{a:.6f}','—' if prev is None else f'{a-prev:+.6f}']);prev=a
write('05-ablation.md','# Абляция: что действительно окупилось\n\n[измерено] cap100, own-trained64KiB, level19, одинаковые события. Каждый вариант переобучен на той же train202; это справедливое равное ресурсное сравнение пакетов, но не изоляция одного бита при неизменном словаре. Строки noef и trailer являются ответвлениями packed, их последовательные разности не следует складывать как независимые эффекты.\n\n'+table(['Корпус','Вариант','Б/соб.','Разность с предыдущей строкой'],rows)+'''
[измерено] На cap500 packed ухудшил base/rich даже после уменьшения raw. На cap100 binary trailer дал небольшой дополнительный выигрыш. Bitmap replay с packed хуже V3 replay на base cap500; упрощённый clean replay лучше. Это опровергает механическое суммирование оценок стадий.

[ограничение] Не построен полный factorial эксперимент всех взаимодействий bool/EF/float/local/string layout. Поэтому не приписываем суммарные проценты отдельному компоненту. Формат и decoder каждого проверенного варианта присутствуют.
'''+table(['Корпус','cap500 V3 replay','V4 clean replay tail','V4 packed replay tail','V4 generic trailer'],[[p,f"{v['V3replay']['B_per_event']:.6f}",f"{v['cleanreplaytail']['B_per_event']:.6f}",f"{v['replaytail']['B_per_event']:.6f}",f"{v['trailer']['B_per_event']:.6f}"] for p,v in x.items()])+'''
[ограничение] Rule1 — только алгоритм исходного синтетического генератора. Для alt предсказаний нет. Матched V3 replay здесь8,331, а не старое8,334: train/selection путь немного иной, сравнивать следует строки одного эксперимента. Упрощённый bitmap выиграл около1,21% base/0,68% rich, не26%. Cap500 не рекомендация для живых редких событий.

[измерено] Два заключительных прохода на validation303 при фиксированном trailer/dict64: ultra22 и LDM19 дали максимум0,00191% и0,00030% соответственно. До них выполнены полные структурные сравнения. Это локальная остановка; непротестированные модели остаются открыты.
''')
rows=[]
for p,v in h['profiles'].items():
 for label,entry in [('small tables12',v['small_tables']['12']),('level1',v['levels']['1']),('level9',v['levels']['9']),('level19',v['levels']['19'])]:
  rows.append([p,label,f"{entry['B_per_event']:.6f}",entry['CCtx_size_max']])
write('08-resource-budget.md','# Память, CPU, очередь и размер библиотеки\n\n[измерено] Holdout909, drift808; выбранный trailer, own dict64, cap100 backlog кроме исходных коротких drift-пачек. CCtx — значение Python zstandard.memory_size после реального сжатия, не RSS приложения, не сумма всего клиента. Числа ниже **в байтах**, не KiB. Дополнительно остаются исходный словарь, объекты событий, выходные буферы, JSON/SQLite/JNI/GC и сетевой стек.\n\n'+table(['Корпус','Профиль','Тело Б/соб.','CCtx bytes max'],rows)+'''
[код] small tables12: level3, window_log17, hash_log12, chain_log12. Это реальная смена параметров и ограничение таблиц матчинга; каждый результат восстановлен. В сравнении с V4 level19 контекст меньше примерно на94–96%, тело на10,0–10,6% больше (для drift+21,8%). Это полезнее для задачи памяти, чем уменьшение буфера на несколько десятков байт.

[измерено] При тех же small-table параметрах V4 против V3 даёт18,419 vs19,384 /41,138 vs43,327 /139,951 vs146,590 Б/соб. CCtx123k vs132k /159k vs172k /310k vs348k. Drift почти равен:36,920 vs36,908, CCtx90,5k vs92,0k. Значит часть выигрыша доступна и V3 простой настройкой компрессора: нельзя всё приписать новому формату.

[измерено] Отдельный stable C API zstd1.5.7, dict64 и12000Б sample: CDict(level19)=1653312Б, CCtx=2328024Б; level9=735808+234464Б; level1=113216+103392Б. byReference убирает ровно65536Б копии словаря, не entropy/match tables. DDict=92888Б. Эти размеры относятся к другому API/параметрам и не складываются со строками Python CCtx. mappable raw dictionary не равен готовому CDict.

## Три решения с разными затратами

[оценка] Простое: оставить MTB2/V3 структуру и применить проверенный low-memory compressor profile; минимальная сложность переноса. При жёстком лимите APK сравнить существующий gzip со zstd, а не автоматически добавлять библиотеку. Фактические gzip6 размеры для V4 также есть в holdout-resources.json.

[оценка] Кандидат V4 для проверки на устройствах: trailer + малые tables12, один переиспользуемый контекст, один активный dictionary, исходная cadence/немедленный Flush; cap100 только доступный backlog. Это выбор в пользу RAM с указанной ценой по сети. Измеренного Android бюджета всей системы пока нет.

[оценка] Предельный по трафику: trailer/level19 при доступном backlog; синтетический clean replay tail/cap500 — отдельный условный опыт. Он требует большей памяти, CPU и известного игрового правила, не заменяет универсальный режим.

## CPU и аллокации

'''+table(['Корпус','Pipeline p50 ms','Pipeline p95 ms','Python peak bytes'],[[p,f"{v['python_pipeline']['uninstrumented_p50_ms']:.3f}",f"{v['python_pipeline']['uninstrumented_p95_ms']:.3f}",v['python_pipeline']['peak_tracemalloc_bytes']] for p,v in h['profiles'].items()])+'''
[измерено] Pipeline = structure encode + один zstd/raw selection + outer decode + весь core parse + byte comparison;30 первых пачек holdout, level9. Timing без tracemalloc; peak измеряется отдельным инструментированным проходом, native allocations в него не входят. Часть прогонов могла делить CPU с независимым V2/native build, поэтому это ориентир стенда, не доказательство ускорения. Нативные compression-only p50/p95 для уровней записаны отдельно. Python prototype сам перебирает integer/float кандидаты и не является быстрым портом C#.

[код] Убрана полная deepcopy для обычного режима; она остаётся только для исследовательского replay. Рекомендуется переиспользовать context (`framing.pack(context=...)`), не запускать четыре компрессора, не держать одновременно все raw/JSON representations в production. В исследовательском oracle дополнительные копии намеренно остаются для проверки.

## Реальная пробная NDK-сборка

'''+table(['Вариант','arm64 .so Б','ZIP Б с headers','Host roundtrips'],[[k,v['raw_bytes'],v['zip_bytes_including_zip_headers'],len(v['host_roundtrips'])] for k,v in nb['variants'].items()])+'''
[измерено] zstd1.5.7 source SHA256 `'''+nb['source_sha256']+'''`, Unity NDK, arm64 API23, Oz/LTO/hidden symbols/gc-sections, три экспортируемых wrapper функции. Android ELF собран и stripped; та же исходная конфигурация на macOS восстановила15 full/3 fast samples через независимый zstd decoder. Fast-only исключает остальные block compressors и предназначен только для быстрого профиля: его116k нельзя приписать level15/19. Native wrapper пока пишет стандартный zstd frame; protocol flags и JNI-порт потребуют проверки размера и совместимости.

[ограничение] Это не APK delta и не готовый Unity плагин; Android ELF не запускался на устройстве. Старый arm64 zstd-jni603960 raw /261876 ZIP и полный AAR1143376Б — разные метрики; AAB обычно доставляет ABI отдельно. Нет оснований обещать4,5× сокращение всего SDK,18KiB IL2CPP или0 GC.

## SQLite: измерение, а не обещание миграции

'''+table(['Корпус','JSON db Б','MessagePack64 db Б','zstd3/dict16 per-row db Б','chunk50 db Б'],[[p,v['json']['db_bytes_checkpointed'],v['msgpack64']['db_bytes_checkpointed'],v['zstd3_dict16_rows']['db_bytes_checkpointed'],v['chunks50_zstd3_dict16']['db_bytes_checkpointed']] for p,v in q.items()])+'''
[измерено] Свежие SQLite db, payload blob+rowid, все source event_id сохранены, WAL отдельно до checkpoint в JSON. Каждый payload восстановлен побайтово. MessagePack без float32 truncation даёт скромную экономию; per-row zstd заметно лучше, но добавляет16KiB словарь/contexts и CPU. Chunk50 сжимает лучше, но меняет единицу ack/deletion/eviction и write amplification.

[ограничение] Это не схема настоящей AnalyticsQueue: нет её индексов/служебных колонок/encryption/fragmentation. Частичный ack требует durable bitmap/rewrite чанка; удалять весь chunk по одному accepted событию нельзя. Миграция, reopen после kill, disk-full и resetIdentity на реальном Android не проверены, поэтому никакая смена storage не внедрена.
''')
write('00-iteration-log.md','''# Журнал фактических итераций

1. Сохранён вход и извлечены два исходных code fence; зафиксированы SHA-256 V2/V3/Runtime/Android source до изменений.
2. Запущены исходные self-tests агента (pass), затем новые контрпримеры (ALP/digest/zlib/integers). Числа V4 из ответа признаны оценками, не воспроизведёнными измерениями.
3. Полностью заново выполнен оригинальный V2 run_all в отдельной копии; сравниваются12 артефактов. V3 test_v3 повторён отдельно.
4. Собраны полный core encoder и независимый bounded decoder, включая bitpacking/EF/float modes/indices/trailer/hash bitmap. Первые тесты нашли ошибку scaled-f32 reconstruction: результат обязательно заново округляется до float32 перед сериализацией. Исправлено и проверено.
5. Первый framing прогон обнаружил несоответствие ожидания единиц max_window_size у установленного Python binding; установлено защитное2MiB значение и отдельный header preflight. Слишком строгая проверка elapsed обнаружила отрицательный -1 в старом генераторе; benchmark сохраняет его как signed, defect документирован.
6. Парная матрица:3 профиля × original/100/500 × dict16/64 × V2/V3/clean/packed, плюс дополнительные варианты cap100 и replay. Каждый V4 кадр распакован и сравнен побайтово с V1-minus-id.
7. На validation303 выбран единый trailer; затем открыт holdout909 и отдельный drift808. Последний выявил регрессию, которая сохранена в отчёте, без подбора его seed или модели.
8. Измерены уровни1/3/6/9/15/19, match tables12/14/16, полная CPU pipeline/Python allocations, native CDict/CCtx/DDict. Эффект RAM не смешивается с размером словаря.
9. Измерены отдельные SQLite storage варианты, HTTP models на равной cadence; создан полный20-event fixture. Header synthesis trial реально сэкономил2байта, но оставлен отдельным опытом.
10. Собраны две compressor-only NDK arm64 библиотеки. Первый host-check упал из-за локального имени z, перекрывшего zstandard объект после ZipFile; переименовано в archive. Повтор подтвердил18 host roundtrips; Android runtime не заявлен.
11. Финальные ultra22/LDM проходы на validation ниже2%; это проверка этих двух опций, не исчерпание всех архитектур. Полноценные Chimp/rANS/FSST/XDelta остаются открытыми направлениями.
12. Добавлены полные request byte-path, exact overlay и SQLite модели durable retries/partial ACK/late response/authorization/conflict. После последних изменений запускаются весь V4 test suite и completion verifier.
''')
write('02-hypotheses.md','''# Гипотезы и статус

|Гипотеза|Статус|Решение|
|---|---|---|
|Убрать duplicate directory/dead kind/dt0|Полный encode/decode и paired frame измерены|Простой clean вариант, малый выигрыш|
|Bitpack/EF поверх varint|Интегрированы, включая sys streams|Не выбирать по raw size без внешнего zstd|
|BOOL1bit|Реализован и fuzz проверен|Не обещать8× уменьшение после zstd|
|Decimal scaling + XOR zeros|Реализованы с exact binary guard|Не называть Chimp128/ALP paper codec|
|Локальные string indices/length split|Реализованы|Вклад в совокупном packed варианте, не additive|
|UUID/HEX raw trailer|Измерен, выиграл validation303|Кандидат V4, не все random fields вынесены|
|Hash bitmap вместо sentinel|Измерен полный conditional roundtrip|На cap500 clean лучше packed; реальное правило неизвестно|
|Zstd header synthesis|Отдельный реальный roundtrip trial|2Б savings, требует fixed negotiated window; не default|
|Малые compression tables|Измерены V3/V4 одинаковые params|Главный доступный ход для RAM с ценой по сети|
|Compressor-only native library|Две настоящие NDK сборки + host tests|Реальный размер; JNI/Android runtime gate открыт|
|MessagePack row / compressed row / chunk50|SQLite payload experiment с roundtrip|Не внедрять без миграции/partial-ACK/crash tests|
|16bit batch MAC|Опровергнута безопасность/полнота input|Immutable request rows; при внешнем binding нужен сильный полный hash|
|Range-only dedup|Не сохраняет conflict detection при overlap/rebatch|Оставить cold per-event evidence, hot range только cache|
|rANS/FSST/Chimp128/game board XDelta|Отсутствуют в коде внешнего агента, здесь не реализованы|Открыто; нет придуманного выигрыша или проигрыша|
''')
write('03-protocol-spec-v4.md','''# MTB4: исследовательский wire-контракт

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

'''+f"Core {ex['core_bytes']}Б, trailer {ex['trailer_bytes']}Б, HTTP body {ex['frame_bytes']}Б.\n\n```text\n{ex['frame_hex']}\n```\n")
write('07-review-guide.md','''# Как независимо проверить V4

1. Прочитать00-summary,01-audit,08-resource-budget: здесь явно отделены фактические результаты от оценок внешнего агента.
2. Открытьreview-input/external-review.md и два исходных Python файла. Запуститьexternal_audit.py: исходные self-tests пройдут, новые контрпримеры покажут дефекты.
3. ВоспроизвестиV2 из v2-rerun/run_all.sh и проверить12 deterministic outputs; логи свежего прогона уже вresults. V3 test_v3.py повторён и дал8233 события.
4. Запуститьtest_v4.py: vectors,profiles,boundaries,exact request bytes,digest,ACK binding,server retries,malformed framing,6000 mutations. Проверять не только compression/decompression, но rendered V1-minus-id bytes.
5. Сверитьpaired-matrix.json: одинаковые cap и dictionary budget, собственное обучение каждого формата. Данные сами воспроизводятся фиксированными seeds. Не суммировать stage savings.
6. Зафиксироватьselection.json до просмотраholdout-resources.json; validation303 выбралаtrailer,909/drift808 не меняют выбор. Убедиться, что drift регрессия не скрыта.
7. СопоставитьRAM с измеряемым объектом: Python CCtx, native CDict+CCtx, source bytes и whole-process RSS — разные величины. Tracemalloc не видит native allocator.
8. Native NDK результат проверить поsource SHA,compiler flags,dynamic symbols,host roundtrips. runtime_tested=false относится к Android ELF; host tests не подтверждают JNI/IL2CPP.
9. Для новой версии обязательно получить реальные queued bytes, auth/migration контракт и Android release telemetry. Без этого нельзя объявлять0 GC,≤192KiB всейRAM или<3.5ms p99.

[ограничение] Mutation fuzz без coverage не доказывает отсутствие уязвимостей. Изменённые payload могут успешно декодироваться; TLS и серверная валидация имеют свои роли. V4 не содержит сервера production и не меняет SDK.
''')
write('08-rollout-plan.md','''# Порядок возможного внедрения

[статус] Этот пакет ничего не выкатывает в продукт. Следующие пункты — требования к отдельному внедрению, не утверждение об их выполнении.

1. Сначала снять Unity/.NET→JSONObject→SQLite→V1 byte oracle на реальных устройствах. Зафиксировать канонизацию numeric lexemes/UTF16 escapes и миграцию event_id↔origin/sequence. Включить lossless shadow roundtrip без изменения отправки.
2. Измерить существующий V3/MTB2 low-memory zstd profile на тех же событиях, включая CPU/p99/peak RSS/APK delta. Если он удовлетворяет целям RAM, это самый простой вариант: перенос нового core необязателен.
3. Сравнить V4 trailer и simple legacy shape на реальном holdout нескольких релизов; предзадать допустимую регрессию сети/CPU. Короткие сессии, редкие события и explicit Flush — самостоятельные strata, а не cap100 склейка.
4. Только после server auth/dedup/limit implementations: небольшой negotiated canary, kill switch, dict fallback, literal/V1 retry, no-delete on malformed ACK. Immutable row binding и closed request callbacks обязательны. Старые dict IDs обслуживаются до закрытия retry horizon.
5. Native wrapper переносится в Unity/JNI с ABI tests, error-path allocation/free tests, thread ownership, symbol/size checks и проверкой Android ELF runtime. Fast-only mode не подменяет полную level15/19 библиотеку.
6. Queue compression — отдельная миграция. Сначала per-row reversible вариант с dual-read и checksum/format version; crash/reopen/disk-full/partial-ACK/quarantine/reset tests. Chunked blobs пока исследование; они не нужны для сетевого V4.
7. Game rule включать только после source audit реальной игры и exact shadow prediction; mismatches уходят literal, не вычисленным значением. СинтетическийSHA rule не становится продуктовым только потому, что он сжалbase.
8. Server cache ограничить byte-budget/LRU; per-origin watermark ускоряет lookup, но durable per-event conflict evidence не удаляется по размеру batch. Измерить cold duplicate lookup IOPS, retention и restore/clone recovery.

[оценка] Go/No-Go задаётся владельцем продукта по фактическим SLO и новым данным. Порог15% hash misses или3.5ms из ответа агента не выводится из имеющихся измерений; их нельзя объявлять универсальными release gates. Оптимум по RAM, CPU и сети — разные точки.
''')
write('09-open-questions.md','''# Что ещё не доказано и потенциальные проблемы

- Нет production corpus, Android CPU/battery/RSS, Unity wire capture и настоящего HTTP replay. Синтетические результаты не переводятся в обещания пользователям.
- На независимом drift V4 хуже V3 на2.34% тела. Даже наличие схемного дрейфа в генераторе не заменяет holdout по реальным релизам/установкам.
- AppVersion/BuildNumber не ограничены текущим SDK. Compact raw bound требует capability/fallback, иначе можно отвергнуть допустимую запись. Общая2MiB quota не является гарантийным максимумом памяти процесса.
- Python core/decoder и exact patcher выделяют списки/словари и сравнивают исходные bytes. Порт обязан сохранять безопасность, но его RAM/CPU/GC не измерены. SequenceMatcher с dense lexical differences может иметь плохую сложность: ограничивать работу и выбирать literal, не блокировать Flush.
- Reference decoder не реализует весь production JSON/schema/auth validator. Literal/overlay output требует самостоятельной валидации, включая n,project/origin и duplicate keys, до dedup/ACK. Это нельзя считать production-hardened parser после6000 random mutations.
- Frame transport передаёт чужое значение dict ID только после pinned manifest check; script dict objects доверенные. Нет полноценного manifest download/signature/atomic-update implementation.
- ACK модель проверяет rows/request mapping, но не настоящий asynchronous HttpClient lifecycle, process-kill междуACK иSQLite commit,JNI или policy discard path. Именно их нужно тестировать при внедрении.
- Durable model хранит identity/digest, не настоящий analytics payload. Production должен атомарно сохранять payload и dedup; отсутствие partial commit доказано лишь в SQLite-модели.
- Origin cloning/restore может создать новые divergence events в старой epoch. Новый origin protocol и авторизация ранее накопленных rows ещё не реализованы. Простой random ID и noBackup не решают все сценарии.
- Range-only dedup,16bit MAC/digest и произвольный TTL не разрешены вместо полной проверки. Hot memory можно уменьшить cold index, но disk/IOPS/retention считаются отдельно.
- История между пачками, full rANS/FSST/Chimp/ALP и board-aware delta остаются открытыми. Нет доказательства глобальной минимальности8.23Б или какой-либо Shannon floor.
- Native source pin/compile проверены, Android runtime/APK delta нет. Full compression wrapper всё ещё не JNI binding; отдельная native library может оказаться дороже существующего gzip на редком трафике.
- SQLite payload experiment не включает служебные столбцы/индексы реальной очереди, её eviction и WAL lifetime. Chunk50 требует per-event ack bitmap и безопасной миграции; коэффициент6–8× нельзя переносить без проверки.
- Число loaded CDict/DDict и concurrently decoded requests доминирует сервернуюRAM. Нужен глобальный pool/tenant quota; per-event raw ceiling не заменяет его.
- Входные V3 генераторы имеют synthetic sent_at+250 и occasional elapsed=-1; source byte oracle и physical deadline должны быть измерены заново.
''')
write('10-sources.md','''# Источники и происхождение доказательств

[локальный первичный] review-input/external-review.md и два извлечённых Python файла — ответ другого агента целиком, неизменённый. Его числа, помеченные расчётом, не считаются измерением; неподдержанные утверждения о выполненных итерациях опровергаются отсутствием соответствующего кода/вывода.

[локальный первичный] ../transport-v2/04-experiments/{gen,wire}.py; ../transport-v3/06-experiments/{codec,frame,bench,alternate,network,test_v3}.py и raw results. V2 свежая копия с полным прогоном находится в06-experiments/v2-rerun. results/input-sha256.json фиксирует исходныеV2/V3/Runtime/Android files до работы; verify.py проверяет неизменность.

[локальный SDK] Runtime/Internal/AnalyticsUploader.cs:SendBatch/ParseAcknowledgement; PersistenceEventSerializer.cs:AppendValue; EventValidator.cs; AnalyticsDeviceContext.cs; Native~/android/analytics/src/main/java/com/daliys/analytics/AnalyticsQueue.java. Это действующие source, не предположение по старой карте проекта.

[внешний первичный] [zstd1.5.7 C API](https://github.com/facebook/zstd/blob/v1.5.7/lib/zstd.h) — context/dictionary APIs, by-reference lifetime, frame output limits. [zstd1.5.7 frame format](https://github.com/facebook/zstd/blob/v1.5.7/doc/zstd_compression_format.md) — FHD/window/block structure. Ссылки проверены при работе; фактические версии pinned в результатах иsource SHA.

[воспроизводимый код] Полные measured JSON/log/binary fixtures в06-experiments/results. requirements.txt закрепляет версии исходного V3 окружения; Python3.14.8/macOSarm64/zstd1.5.7 — реально проверенная среда. NDK revision записан вnative-build.json. Другие платформы не проверены.

[метод] Train202/18 installs, исследовательское сравнение101/6, validation303/3, holdout909/6; новыйdrift808/4×600 с отдельным train202. Все corpus shapes и seeds заданы вworkloads.py, никакого поиска выгодных seed нет. Drift не заимствует игровую грамматикуV2; поля совместимы с логической моделью SDK, но ни один генератор не является production capture.
''')
net=load('network-v4.json');rows=[]
for pattern,vs in net['patterns'].items():
 v=vs['30000'];a=v['models']['V3'];b=v['models']['V4'];rows.append([pattern,v['batches'],f"{a['body_B_per_event']:.3f}",f"{b['body_B_per_event']:.3f}",f"{a['wire_B_per_event']['h2_setup0']:.3f}",f"{b['wire_B_per_event']['h2_setup0']:.3f}"])
with (D/'08-resource-budget.md').open('a') as out:
 out.write('\n## Полная транспортная модель\n\n[модель] Равные события/cadence, deadline30s, source base101×900, собственные target100/dict64/level19, ACK2Б. HPACK authorization never-indexed измерен, TCP/IP/TLS/H2 bytes и setup — явные допущения старого network.py, не packet capture. Подробные H1/H2/H3 и setup0/750/4500 при deadline30/60/120s доступны вnetwork-v4.json.\n\n'+table(['Arrival','Пачек','V3 body Б/соб.','V4 body','V3 warm H2 total','V4 warm H2 total'],rows)+'\n[модель] Sparse45s остаётся дорогим: уменьшение body на8Б не убирает сотни байт заголовков. Заявленного агентом single-event fast header и62Б выигрыша здесь нет. Offline900 cap100 использует имеющийся backlog; это не обещание нулевой online latency. H3 не добавляет поверх QUIC фиктивные TLS records.\n')
low=load('memory-floor.json');rows=[]
for p,vs in low.items():
 v=next(v for v in vs if v['dictionary_bytes']==16384 and v['hash_log']==10);rows.append([p,v['CCtx_size_max'],v['dictionary_bytes'],f"{v['B_per_event']:.6f}"])
with (D/'08-resource-budget.md').open('a') as out:
 out.write('\n## Дополнительный поиск минимального контекста\n\n[измерено] После основной матрицы отдельно проверены fast strategy, window_log14, hash/chain10/11/12 и dictionary16/64 наvalidation303. Это ресурсное исследование наvalidation, **не новый результат нетронутогоholdout** и не смена выбраннойtrailer модели. Минимальная проверенная точка, не доказанный глобальный минимум:\n\n'+table(['Корпус','CCtx max Б','Dictionary source Б','Тело Б/соб.'],rows)+'\n[измерено] По сравнению сtrailer/level19 натойжеvalidation тело увеличилось на14,5% /16,9% /21,6%. Словарь64КиБ не улучшил эти очень малые окна: вдвое и вчетверо большийdictionary не обязан помогать. Дополнительные buffer/JSON/SQLite/native code pages по-прежнему не входят вCCtx. Этаfast стратегия совместима по классу скомпактной116k библиотекой, но её wrapper ещё требует переноса точныхcustom parameters; нельзя объединять два измерения и заявлять готовыйSDK peak96KiB. Все18 конфигураций восстановили исходныйcore иtrailer.\n')
