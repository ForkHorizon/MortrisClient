"""Regenerate numerical report sections from raw results; no measurements invented."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent;DOC=ROOT.parent
B=json.loads((ROOT/'results/bench.json').read_text())['profiles'];R=json.loads((ROOT/'results/refine.json').read_text());E=json.loads((ROOT/'results/extreme.json').read_text());F=json.loads((ROOT/'results/further.json').read_text());X=json.loads((ROOT/'results/extras.json').read_text());N=json.loads((ROOT/'results/network.json').read_text())
profiles=['base','rich','alt']
def vals(key):return ' | '.join(f"{B[p]['body_B_per_event'][key]:.3f}" for p in profiles)
def row(label,key):return f'| {label} | {vals(key)} |\n'
header='| Вариант | base Б/соб. | rich Б/соб. | alt Б/соб. |\n|---|---:|---:|---:|\n'
options='''# Варианты и решения

[измерено] `bench.py`, `refine.py`, `extreme.py`, raw `results/{bench,refine,extreme}.json`. Один test seed101 и train202: 6/18 установок, соответственно 8944 /7899 /5400 test событий. Base/rich — два профиля первого генератора; alt — независимая логика. Включена внешняя рамка каждого протокола. Словари обучены отдельно по представлению; реальные данные отсутствуют.

'''+header
for label,key in [('Сегодняшний V1 JSON gzip1','V1_gzip1'),('V1 gzip6 (консервативный шаг без нового codec)','V1_gzip6'),('V2 dict16 level19, прежние пачки','V2_dict16_l19'),('V3 консервативный: dict64, прежние пачки','V3_same_batches'),('V3 cap100 с прежним обучением dict64','V3_batch100')]:options+=row(label,key)
options+='| **V3 рекомендуемый: cap100, dict64 обучен на100** | '+' | '.join(f"{R[p]['best']:.3f}" for p in profiles)+' |\n'
options+=row('V3 cap500, общий, без игровых правил','V3_batch500')
options+='| **V3 предельный: cap500 + rule1, собственный dict64** | '+' | '.join(f"{E[p]['B_event']:.3f}" for p in profiles)+' |\n\n'
for p in profiles:
 d=B[p]['body_B_per_event'];options+=f"[измерено] {p}: рекомендуемый −{100*(1-R[p]['best']/d['V2_dict16_l19']):.1f}% к V2 и −{100*(1-R[p]['best']/d['V1_gzip1']):.1f}% к V1. Предельный −{100*(1-E[p]['B_event']/d['V2_dict16_l19']):.1f}% к V2.\n\n"
options+='''[оценка] cap100/500 — кривая при наличии соответствующей очереди, **не обещание** для коротких/редких сессий. Для прежней cadence переносимый результат — строка консервативного V3. Предельная точка использует известный алгоритм синтетического хеша; для alt rule ничего не удаляет. Её ограничивают snapshot/history metadata, случайные float/time/opaque values, latency/CPU cap500 и наличие достоверной rule manifest. Это не универсальный entropy floor.

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

'''
options+=header
for label,key in [('V2 dict16','V2_dict16_l19'),('Linear predictor','linear'),('Per-type predictor','per_type'),('XOR float proxy','xor'),('Prefix strings','prefix'),('Hash replay only','replay_hash'),('Brotli11','V2_brotli11'),('PPMd8 batch','V2_ppmd8'),('PPMd12 whole install','ppmd_whole_install')]:options+=row(label,key)
options+='\n[измерено] Контекстная арифметика (bytes на подкорпусе, один и тот же набор входов внутри строки):\n\n| Профиль | AC byte context | zstd+dict16 | AC field/type/previous-type | zstd values безdict | field prior JSON bytes |\n|---|---:|---:|---:|---:|---:|\n'
for p in profiles:
 a=B[p]['arithmetic'];f=F[p]['field_arithmetic'];options+=f"| {p} | {a['bytes']} | {a['zstd_bytes']} | {f['bytes']} | {f['zstd_no_dict_bytes']} | {f['model_json_bytes']} |\n"
options+='\n[измерено] Markov cross-entropy, не размер готового самостоятельного кадра:\n\n| Профиль | unigram бит/event | Markov1 | ngram2 |\n|---|---:|---:|---:|\n'
for p in profiles:options+='| '+p+' | '+' | '.join(f'{v:.4f}' for v in B[p]['type_model_bits_per_event'])+' |\n'
options+='\n[измерено] История и multi-dictionary на отдельном подкорпусе2install (не сравнивать абсолютные B/event с6install таблицей выше):\n\n| Профиль | stateless16 |3×dict16 |history4 ref8 |miss1% |miss5% |miss20% |\n|---|---:|---:|---:|---:|---:|---:|\n'
for p in profiles:
 f=F[p];m=f['history_with_reference_miss_B_event'];options+=f"| {p} | {f['dict16_B_event']:.3f} | {f['multi3_dict16_B_event']:.3f} | {f['history4_B_event']:.3f} | {m['0.01']:.3f} | {m['0.05']:.3f} | {m['0.2']:.3f} |\n"
options+='\n[оценка] p здесь вероятность **утраченной reference**, не packet loss: обычный TCP retry не равен resync. Цена дополнительного RTT и headers сверху не включена: измерение благоприятно истории. Stateful остаётся непринятым в базовую рекомендацию, но не объявлен бесполезным.\n'
options+='\n[измерено]/[оценка] Integer value stage: varint exact counts, bitpack/EF formula sizes, bitmap set proxy (порядок не сохраняет):\n\n| Профиль |varint bytes|bitpack bytes|EF applicable varint|EF bytes|bitmap set bytes|\n|---|---:|---:|---:|---:|---:|\n'
for p in profiles:
 f=F[p]['integer_columns'];options+='| '+p+' | '+' | '.join(str(f[k]) for k in ['varint','bitpack','ef_applicable_varint','ef','bitmap_set'])+' |\n'
C=json.loads((ROOT/'results/checkpoint.json').read_text())
options+='\n[измерено] Sparse string edits + anchor per batch (не whole-frame):\n\n| Профиль | literals zstd19 | sparse zstd19 | change |\n|---|---:|---:|---:|\n'
for p,c in C.items():options+=f"| {p} |{c['zstd_literals_bytes']}|{c['zstd_sparse_bytes']}|{100*(c['zstd_sparse_bytes']/c['zstd_literals_bytes']-1):+.1f}%|\n"
options+='''
[оценка] Встраивание rule/model update: patch29KiB при s=0,5Б/event требует≈60тыс событий до окупаемости. Частые обновления на коротких сессиях могут съесть всю экономию. Статические таблицы/словарь — часть SDK download budget, а не бесплатные байты вне отчёта.

## Полный транспортный бюджет

[измерено] Header block HPACK с never-indexed Authorization:67/49/49Б. [оценка] Модель `network.py`: IPv4 TCP52Б, TLS22Б/record, MSS1400, request+response и по одному pureACK каждого направления; H1 req170/resp90, H2 framing18/направление, H3 QPACK такой же49Б как параметр, framing6/направление, UDP+QUIC79Б/packet, datagram1200 и2ACK. TLS setup0/750/4500Б **на соединение**; таблица cold предполагает новое соединение на каждую пачку, не утверждает что так работает SDK. H3 overhead задан оценкой, не pcap. Полный TLS с публичными хостами воспроизведён V2 скриптом, аналитический endpoint не измерен.

'''
options+='| Приход событий | deadline | mean batch | body Б/event | warmH1 всё | warmH2 всё | warmH3 всё | coldH2 setup4500 |\n|---|---:|---:|---:|---:|---:|---:|---:|\n'
for p,rows in N['patterns'].items():
 for deadline,r in rows.items():
  if deadline=='60000' and p in ('short_8','offline_900'):continue
  if deadline=='120000' and p in ('short_8','offline_900'):continue
  t=r['total_B_event'];options+=f"|{p}|{int(deadline)//1000}с|{r['mean_batch']:.1f}|{r['body_B_event']:.2f}|{t['h1_setup0']:.2f}|{t['h2_setup0']:.2f}|{t['h3_setup0']:.2f}|{t['h2_setup4500']:.2f}|\n"
options+='\n[оценка] Сессионное возобновление750Б даёт промежуточные значения (полные числа в network.json). При full-request retry probability1/5/20% множитель байтов1,0101/1,0526/1,25; не смешивать с потерями TCP segments. Реальные arrival/session/connection distributions неизвестны: latency win и cold доли нельзя вывести из синтетики.\n'
(DOC/'04-options-comparison.md').write_text(options)
ablation='''# Парная абляция и сумма шагов

[измерено] `bench.py`+`refine.py`, фиксированные test/train, единица — сумма тел/сумма событий. Каждая строка включает framing. Абсолютная база одна; delta строки считается от предыдущей. Проценты отдельных вариантов не складываются. 64KiB normal dictionary обучен на прежних границах; target dictionary на rebatch100. Полный V2 воспроизведён отдельно, здесь seed101/202 даёт новые числа.

'''
for p in profiles:
 d=B[p]['body_B_per_event'];steps=[('V1 gzip1',d['V1_gzip1']),('V2 dict16 level19',d['V2_dict16_l19']),('dict64, пока V2 framing',d['V2_dict64']),('V3 рамка + safe selection, прежние пачки',d['V3_same_batches']),('V3 rebatch100, прежний dict64',d['V3_batch100']),('V3 dict64 trained100',R[p]['best'])]
 ablation+=f'## {p}\n\n|Шаг|Б/event|Δ Б от предыдущего|Δ% от предыдущего|Экономия к V1|\n|---|---:|---:|---:|---:|\n';prev=None
 for label,v in steps:
  diff='—' if prev is None else f'{v-prev:+.3f}';pct='—' if prev is None else f'{100*(v/prev-1):+.2f}%'
  ablation+=f'|{label}|{v:.3f}|{diff}|{pct}|{100*(1-v/steps[0][1]):.2f}%|\n';prev=v
 ablation+='\n'
ablation+='''[оценка] Frame/raw-length добавляет около3Б/пачка сверх V2; это плата за явную границу доверия, не оптимизация. Смена shape/context и UUID исключение уже были в V2 и повторно не приписаны V3. Уменьшение числа запросов и изменение обучения — два разных шага. Target-size training почти бесплатно по runtime, но требует holdout не только того же генератора.

[измерено] Leave-one-feature-out V2 исходного автора подтверждён полным run_all. Его row-major24,9 со своимdict и25,7 с columnardict — разные условия; в этой абляции их нет. Вклад изменения компрессора вместе с dictionary не объявляется вкладом только dictionary.

[измерено] Условная extreme точка8,334/29,088/123,045 включает cap500, специально обученный64KiB dictionary и rule1+anchor: это **совместный** эксперимент. Нельзя вычитать из него hash-only effect17,931/42,360/143,463 с прежних пачек и утверждать additive attribution. General cap50015,265/36,020/123,729 использует иной training; полная парная hash ablation с одинаковой тренировочной процедурой — следующий вопрос. Roundtrip extreme проверен независимо от размеров.

[оценка] Увеличение пачки без изменения freshness возможно только для backlog. Для остальных событий bytes/latency tradeoff в network.py. Это не обещание universal −25% без дополнительных условий.
'''
(DOC/'05-ablation.md').write_text(ablation)
summary=['# Transport V3 — вывод','','[измерено] Числа V2 воспроизвелись:12 детерминированных артефактов совпали байт в байт.','[измерено] Обещание общего byte-exact V2 опровергнуто: double.MaxValue, CTXREF120.0→120; oracle не проверял Unity/Android.','[измерено] Независимый alt снижает выигрыш V2 к V1 с72–80% до43%; перенос на продакшен неизвестен.','[код] Энтропийный floor≈11Б ошибочен: хеш генератора вычислим по переданным входам.','[оценка] Рекомендуется V3: строгая рамка+literal fallback, immutable origin/seq, request-bound ack,64KiB dictionary trained на cap100.']
for p in profiles:
 d=B[p]['body_B_per_event'];summary.append(f"[измерено] {p}: V1 {d['V1_gzip1']:.2f} → V2 {d['V2_dict16_l19']:.2f} → V3 {R[p]['best']:.2f} Б/event (−{100*(1-R[p]['best']/d['V2_dict16_l19']):.1f}% к V2; −{100*(1-R[p]['best']/d['V1_gzip1']):.1f}% к V1), если доступны пачки100.")
summary+=['[измерено] Без смены cadence V3:21,76/44,86/138,42 Б/event, выигрыш3,5–6,2% к V2.','[измерено] Предельный cap500+синтетический hash rule:8,33/29,09/123,04 Б/event; не доказан для реальной игры.','[измерено] Проверены8233 событий V3 и2000 мутаций внешней рамки; full-device/серверного теста нет.','[оценка] Риски: native≈604КБ raw arm64 +64КБ dictionary, unknown phone CPU/battery, словарь/corpus drift, latency, V1/V3 dedup migration.','[оценка] Нужны реальные payloads+wire capture и Android gates из08/09; продуктовый код и V2 не изменялись.']
(DOC/'00-summary.md').write_text('\n'.join(summary)+'\n')
spec=DOC/'03-protocol-spec-v3.md';s=spec.read_text().split('<!--GENERATED-->')[0];ex=X['example'];f=bytes.fromhex(ex['hex']);s+='<!--GENERATED-->\n\n'
s+=f"[измерено] V1 безevent_id {ex['raw_v1_bytes']}Б → payload {ex['payload_bytes']}Б → frame {ex['frame_bytes']}Б = {ex['B_event']:.2f}Б/event. Prefix `32 01 01 97 0c`: zstd,kind1,dict1,raw_len1559; header5Б, compressed body467Б. SHA256 frame `{ex['frame_sha256']}`.\n\n```text\n"
for i in range(0,len(f),16):s+=f'{i:04x}  '+f[i:i+16].hex(' ')+'\n'
s+='```\n\n[измерено] Восстановление: `.venv/bin/python extras.py`, либо `frame.unpack(example_frame,{1:dict}) → wire.mtb2_decode(payload) → wire.v1_json(...,without_event_id=True)`; сравнить с `results/example-v1.json`. Настоящий sent_at/SDK serializer проверяется отдельно на реальном корпусе, этот fixture использует V2 synthetic conventions.\n'
spec.write_text(s)
