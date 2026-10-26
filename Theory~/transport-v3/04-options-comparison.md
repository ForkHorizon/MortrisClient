# Варианты и решения

[измерено] `bench.py`, `refine.py`, `extreme.py`, raw `results/{bench,refine,extreme}.json`. Один test seed101 и train202: 6/18 установок, соответственно 8944 /7899 /5400 test событий. Base/rich — два профиля первого генератора; alt — независимая логика. Включена внешняя рамка каждого протокола. Словари обучены отдельно по представлению; реальные данные отсутствуют.

| Вариант | base Б/соб. | rich Б/соб. | alt Б/соб. |
|---|---:|---:|---:|
| Сегодняшний V1 JSON gzip1 | 113.766 | 172.365 | 251.995 |
| V1 gzip6 (консервативный шаг без нового codec) | 98.161 | 145.160 | 227.237 |
| V2 dict16 level19, прежние пачки | 22.839 | 47.813 | 143.463 |
| V3 консервативный: dict64, прежние пачки | 21.756 | 44.856 | 138.418 |
| V3 cap100 с прежним обучением dict64 | 17.800 | 39.812 | 129.568 |
| **V3 рекомендуемый: cap100, dict64 обучен на100** | 17.051 | 38.084 | 129.506 |
| V3 cap500, общий, без игровых правил | 15.265 | 36.020 | 123.729 |
| **V3 предельный: cap500 + rule1, собственный dict64** | 8.334 | 29.088 | 123.045 |

[измерено] base: рекомендуемый −25.3% к V2 и −85.0% к V1. Предельный −63.5% к V2.

[измерено] rich: рекомендуемый −20.3% к V2 и −77.9% к V1. Предельный −39.2% к V2.

[измерено] alt: рекомендуемый −9.7% к V2 и −48.6% к V1. Предельный −14.2% к V2.

[оценка] cap100/500 — кривая при наличии соответствующей очереди, **не обещание** для коротких/редких сессий. Для прежней cadence переносимый результат — строка консервативного V3. Предельная точка использует известный алгоритм синтетического хеша; для alt rule ничего не удаляет. Её ограничивают snapshot/history metadata, случайные float/time/opaque values, latency/CPU cap500 и наличие достоверной rule manifest. Это не универсальный entropy floor.

## Все обязательные направления

Для каждой строки: гипотеза → ожидаемый вклад → факт/расчёт → стоимость → решение. Проценты относятся к соответствующей базе; их нельзя складывать. Отсутствующие аппаратные CPU/code-size числа не выданы за измеренные.

| Идея | Гипотеза/ожидание | Замер или оценка, границы | CPU / SDK / сложность / риск | Решение |
|---|---|---|---|---|
| Контекстная арифметика по байтам | [гипотеза] выигрыш20–35% как предполагал V2 | [измерено] bench arithmetic: реальные encode/decode8 пачек/profile; ниже таблица. Проигрыш zstd, несмотря на prior | Python десятки мс/пачка; prior JSON сотниКБ; fixed integer decoder свой | Отклонить эту модель; не все arithmetic/ANS модели |
| Поле+тип события+предыдущий тип, предыдущий байт | [гипотеза] field context уберёт ошибки общей модели | [измерено] further field_arithmetic, value stage only, ниже; нет выигрыша даже без всей схемы | Больше sparse tables, 0,1–0,3с Python; table bytes указаны; C#/Java size не измерен | Отклонить этот прототип |
| ANS вместо arithmetic | [оценка] одинаковая вероятность даёт близкую длину в пределах termination/table overhead | Кодера ANS нет: только estimate той же cross-entropy. Замена entropy backend не исправит плохую модель | Таблицы и переносимый integer decoder; нативная зависимость опциональна | Нужны реальные данные/лучшая модель, не заявлен measured ANS win |
| Марков/n-gram типа | [гипотеза] цепочка→доли бита | [измерено] обученный Markov/n-gram cross-entropy, ниже; это оценка кода без manifest/reset overhead | Операции table lookup;10–80 типов; new names escape; переобучение по игре без ручной цепочки | Не отдельный codec: верх экономии типа уже частично съеден zstd |
| Линейное/по типу предсказание int | [гипотеза] residual меньше обычной delta | [измерено] свои dict16 и matched dict64/cap100, ниже; лучшая matched модель не улучшает все корпуса | 2 последних значения/поле, O(fields); mode metadata и overflow; generic | Не включать |
| Gorilla/Chimp/Elf-подобное float предсказание | [гипотеза] близкие float дешевле | [измерено] только XOR64→varint proxy, ниже; полный Chimp/Elf не реализован. Случайные mantissa генератора неблагоприятны | Несколько ops/value, собственные typed bitstreams; signed0/NaN и exact lexeme | Proxy отклонить; полные codecs требуют реальных float columns |
| Статический prior вместо dictionary | [гипотеза] таблица компактнее64KiB и точнее LZ | [измерено] prior sizes из arithmetic tests; распределение по полям разрежено; JSON представление таблицы не минимально | Код arithmetic около2,5KiB Python исходника, binary/managed size неизвестен; модель может быть сотниКБ | Доказанного выигрыша нет |
| Компактный neural predictor | [оценка] 1024 int8 weights≈1KiB, 1–10тыс MAC/event, один prior/output | Не обучался; при экономии0,1Б/event загрузка модели1KiB окупится≈10тыс событий; input/tokenization overhead не включён | Deterministic quantized inference, bounds, cross-platform parity; code cost неизвестен | Нужны реальные данные; не внедрять на основании нейросетевого обещания |
| cmix/PAQ/PPMd ориентир | [гипотеза] более сильный compressor покажет запас | [измерено] PPMd8 на пачках и PPMd12 whole-install ниже. [источник] cmix рекомендует32GB RAM; не запускался | PPMd native измерен; cmix/PAQ не мобильный baseline; neural quality не измерена | Использовать как ориентир, не «теоретический потолок» |
| Grammar/schema tree | [гипотеза] схемы устранят повтор key names | [код] V2 shapes уже грамматика, nested values текущий validator не поддерживает. [оценка] заранее известные ID могут убрать10–80Б metadata/пачка≈0,1–0,8Б/соб при100, не измеренный выигрыш | Manifest1KiB окупится после1280–10240 событий; registry/miss/release coupling | Inline shapes оставить; внешний registry только после реального измерения |
| Пер-типовые колонки | [гипотеза] однородные контексты лучше | [измерено] per_type predictor действительно разделяет numeric history по имени, но не перестраивает весь формат; row/column baseline V2 воспроизведён | Больше column directory и state; маленькие группы ухудшают статистику | Нет основания принять полный per-type format; не смешивать proxy с готовым codec |
| Кросс-колоночные copy/function | [гипотеза] B=A, B=40−A, elapsed≈time | [код] ALIAS/CTXREF уже есть; [оценка] один1Б checkpoint counter даёт максимум≈0,25Б/event raw на4-событийную группу, после zstd меньше. elapsed residual нельзя выкинуть | Declarative typed rule+equality guard+literal; unknown rule fallback | Copy оставить с проверкой типа; функции только с corpus proof |
| placed_state_hash reconstruction | [гипотеза] убрать непредсказуемый32Б литерал | [измерено] replay_hash и extreme frame roundtrip; начальные/непредсказанные хеши передаются, не исчезают | SHA256 на удачный ход; manifest, game algorithm correctness; one anchor/batch | Только условный extreme, реальный алгоритм неизвестен |
| Intent replay | [оценка] передавать достаточные inputs вместо событий | В gen после initial hash условные256 бит/hash=0; cap500 rule даёт8,33Б/base, но полный replay всех событий не сделан | Вся детерминированная игра+RNG+timestamps+версии; device-dependent inputs требуют residual | Отклонить как универсальный SDK; rule1 — узкое доказательство |
| Interaction frames | [оценка] type transitions2,49→0,28бит, ~0,28Б/event до overhead | [измерено] Markov данные ниже; codec V2 уже общие property columns. На границе пачки/kill незавершённую группу надо сохранить | Buffered grouping только на upload, durable отдельные events; generic grammar обучение | Отдельный game frame пока не оправдан |
| Checkpoint deltas + snapshots | [гипотеза] sparse board600Б меняется мало | [измерено] checkpoint.py exact same-length edits+literal на string value stage, ниже; generic вариант хуже LZ. Prefix тоже хуже | Anchor per batch, O(string length); cross-batch snapshot добавляет recovery | Отклонить проверенные generic варианты; field-specific board delta нуждается в реальной структуре |
| Zstd64 vs16 | [гипотеза] metadata/остатки лучше покрыты | [измерено] одинаковые пачки −5,2%base/−6,4%rich/−3,6%alt до V3 framing | +48KiB dictionary; cache/CDict memory и phone CPU неизвестны | Принять при APK budget |
| Обучение на целевом cap100 | [гипотеза] offsets/table distribution зависит от cap | [измерено] refine:17,80→17,05;39,81→38,08;129,57→129,51; те же тестовые события | Никакого нового runtime code; corpus/version control | Принять: лучший простой новый шаг |
| Несколько словарей по типу пачки | [гипотеза] tiny/medium/large составы различаются | [измерено]3×16KiB vs1×16KiB, further: ниже; выигрыш≤0,14%, rich хуже | +32KiB SDK, training/selection, IDs; без качества на holdout риск | Отклонить этот classifier |
| Zstd ultra22 / LDM | [гипотеза] длиннее поиск→меньше bytes | [измерено] gains≈0% на small frames, refine и final-passes. Длинная history — отдельная задача | Level22 CPU выше, LDMwindow memory; phone не измерен | Отклонить |
| Brotli встроенный dictionary | [гипотеза] text/natural keys помогут | [измерено] q5/q11 ниже; alt q11≈V2dict16, но хуже dict64. Custom external Brotli в Python API не испытывался | q11дороже, отдельный decoder; без trained distribution | Как fallback можно, в recommended нет |
| FSST | [оценка] 1-byte коды1–8-byte phrases на длинных строках | Не запускался:256 entries×(8+length)≈2304Б local table =23Б/event при100 до сжатия; pretrained table снижает этот overhead. Randomhex уже binary в V2, дополнительная Shannon экономия0 | Быстрый random access здесь не нужен; ещё native/codebook. Сравнение полного FSST остаётся открытым | Нужны реальные строки; не выдавать estimate за отрицательный benchmark |
| Bit packing | [гипотеза] узкие int дешевле8bit varint | [измерено] uncompressed column counts further ниже; верхняя граница raw экономии, zstd уже entropy-codes | Width+count и tail, O(n); full-frame gain не измерен | Нужны реальные данные/полный codec; не складывать raw savings с compressed |
| Elias-Fano | [гипотеза] monotone counters/gaps | [измерено] только sorted применимые колонки, дальше byte estimate формулы; sequence почти бесплатный first+gaps | Не применим к float/неупорядоченному типу; first/base overhead малых пачек | Не добавлять к уже компактному sequence; generic numeric verdict открыт |
| Roaring-like | [гипотеза] bitmap sparse ids/ack exceptions | [измерено] размер set-container proxy ниже; он теряет порядок/повторы, поэтому НЕ lossless замена колонке | Для ack exceptions при500 достаточно bitmap63Б+header; при0 ошибок ноль | Только exception bitmap при большом nerrors; не event columns |
| Delta словаря/модели | [гипотеза] не скачивать64К заново | [измерено] patch между независимыми dict corpora≈29–30КБ, не «старение версии»; self-patch21Б — sanity check | SHA256+manifest+bounded output+atomic update, модель отдельный ID | Условно; экономический порог D/s и real-version test |
| Объединение пачек/адаптивная cadence | [гипотеза] amortize тела/headers/radio | [измерено] capcurve; [оценка] dense/sparse/short/offline network models ниже | Latency/retention/product SLO; background flush, CPU cap | Принять cap100 при наличии backlog, deadline только по SLO |
| HTTP2 / HTTP3 / TLS resumption | [гипотеза] снизить fixed overhead | [измерено] HPACK never-indexed67/49/49Б request block; [оценка] network model | Unity/ALPN/keepalive реализация неизвестны; H3 отдельная зависимость | H2/reuse/resume по доступности, H3 ради размера не нужен |
| Минимальный request-bound ack | [оценка] не echo уже известные sequences | Spec ack2Б при малой epoch, counted encoded example30 01; V1 response schema/UUID corpus известны, production compression нет | Immutable in-flight row list и строгая привязка HTTP stream | Принять при durable-commit семантике |
| Piggyback policy/register | [оценка] убрать отдельные polls во время активности | network.py:800Б/полчаса не использовано; явное допущение800Б за3600с даёт0,22Б/event при1Hz,10Б при1/45Hz,66,7 при1/300Hz | Bootstrap и idle policy deadline остаются; auth rotation/policy size | Принять активный piggyback, не обещать отменить bootstrap |
| Межпакетная история | [гипотеза] сильнее прошлой единственной пачки | [измерено]4ack payload history+ref8Б, below; miss p=0/1/5/20%. Компрессорная модель, не crash-safe state-machine | Persistence snapshots, duplicate ack, cache TTL; keyed metadata/abuse budget | Опция для offline backlog; универсальное отклонение V2 слишком сильное |

## Числа для проверки решений

| Вариант | base Б/соб. | rich Б/соб. | alt Б/соб. |
|---|---:|---:|---:|
| V2 dict16 | 22.839 | 47.813 | 143.463 |
| Linear predictor | 22.722 | 47.165 | 143.175 |
| Per-type predictor | 23.102 | 47.922 | 144.126 |
| XOR float proxy | 24.706 | 52.612 | 144.868 |
| Prefix strings | 26.162 | 52.545 | 151.816 |
| Hash replay only | 17.931 | 42.360 | 143.463 |
| Brotli11 | 38.606 | 67.103 | 143.234 |
| PPMd8 batch | 41.070 | 70.453 | 150.319 |
| PPMd12 whole install | 18.640 | 40.010 | 129.749 |

[измерено] Контекстная арифметика (bytes на подкорпусе, один и тот же набор входов внутри строки):

| Профиль | AC byte context | zstd+dict16 | AC field/type/previous-type | zstd values безdict | field prior JSON bytes |
|---|---:|---:|---:|---:|---:|
| base | 8703 | 5075 | 12629 | 4091 | 244214 |
| rich | 15648 | 9533 | 16676 | 8267 | 338211 |
| alt | 46465 | 31864 | 38164 | 27358 | 2637199 |

[измерено] Markov cross-entropy, не размер готового самостоятельного кадра:

| Профиль | unigram бит/event | Markov1 | ngram2 |
|---|---:|---:|---:|
| base | 2.4869 | 0.2754 | 0.2821 |
| rich | 2.4889 | 0.2754 | 0.2815 |
| alt | 3.1347 | 3.0713 | 3.3230 |

[измерено] История и multi-dictionary на отдельном подкорпусе2install (не сравнивать абсолютные B/event с6install таблицей выше):

| Профиль | stateless16 |3×dict16 |history4 ref8 |miss1% |miss5% |miss20% |
|---|---:|---:|---:|---:|---:|---:|
| base | 21.778 | 21.771 | 20.019 | 20.237 | 21.108 | 24.374 |
| rich | 47.759 | 48.324 | 45.583 | 46.061 | 47.971 | 55.135 |
| alt | 145.651 | 145.455 | 134.821 | 136.277 | 142.103 | 163.951 |

[оценка] p здесь вероятность **утраченной reference**, не packet loss: обычный TCP retry не равен resync. Цена дополнительного RTT и headers сверху не включена: измерение благоприятно истории. Stateful остаётся непринятым в базовую рекомендацию, но не объявлен бесполезным.

[измерено]/[оценка] Integer value stage: varint exact counts, bitpack/EF formula sizes, bitmap set proxy (порядок не сохраняет):

| Профиль |varint bytes|bitpack bytes|EF applicable varint|EF bytes|bitmap set bytes|
|---|---:|---:|---:|---:|---:|
| base | 25553 | 14885 | 12368 | 4110 | 13082 |
| rich | 50760 | 33407 | 17688 | 6404 | 31506 |
| alt | 5144 | 2351 | 5144 | 1248 | 2658 |

[измерено] Sparse string edits + anchor per batch (не whole-frame):

| Профиль | literals zstd19 | sparse zstd19 | change |
|---|---:|---:|---:|
| base |38588|41059|+6.4%|
| rich |96547|102821|+6.5%|
| alt |246951|260405|+5.4%|

[оценка] Встраивание rule/model update: patch29KiB при s=0,5Б/event требует≈60тыс событий до окупаемости. Частые обновления на коротких сессиях могут съесть всю экономию. Статические таблицы/словарь — часть SDK download budget, а не бесплатные байты вне отчёта.

## Полный транспортный бюджет

[измерено] Header block HPACK с never-indexed Authorization:67/49/49Б. [оценка] Модель `network.py`: IPv4 TCP52Б, TLS22Б/record, MSS1400, request+response и по одному pureACK каждого направления; H1 req170/resp90, H2 framing18/направление, H3 QPACK такой же49Б как параметр, framing6/направление, UDP+QUIC79Б/packet, datagram1200 и2ACK. TLS setup0/750/4500Б **на соединение**; таблица cold предполагает новое соединение на каждую пачку, не утверждает что так работает SDK. H3 overhead задан оценкой, не pcap. Полный TLS с публичными хостами воспроизведён V2 скриптом, аналитический endpoint не измерен.

| Приход событий | deadline | mean batch | body Б/event | warmH1 всё | warmH2 всё | warmH3 всё | coldH2 setup4500 |
|---|---:|---:|---:|---:|---:|---:|---:|
|dense_1s|30с|30.0|23.07|40.20|35.03|36.37|185.03|
|dense_1s|60с|60.0|19.64|28.50|25.62|27.26|100.62|
|dense_1s|120с|100.0|18.37|24.03|22.48|23.15|67.48|
|sparse_45s|30с|1.0|214.91|728.91|573.91|613.91|5073.91|
|sparse_45s|60с|2.0|126.90|383.90|306.40|326.40|2556.40|
|sparse_45s|120с|3.0|96.59|267.93|216.26|229.59|1716.26|
|short_8|30с|8.0|44.16|108.70|89.23|94.26|654.23|
|offline_900|30с|100.0|18.37|24.03|22.48|23.15|67.48|

[оценка] Сессионное возобновление750Б даёт промежуточные значения (полные числа в network.json). При full-request retry probability1/5/20% множитель байтов1,0101/1,0526/1,25; не смешивать с потерями TCP segments. Реальные arrival/session/connection distributions неизвестны: latency win и cold доли нельзя вывести из синтетики.
