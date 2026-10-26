"""Keep an experimental raw-codec result separate from actual M7/native evidence."""
import json
from support7 import ROOT

def run():
    rows=json.loads((ROOT/'results/cross-benchmark.json').read_text())
    assert [r['variant']for r in rows]==['raw','all_clean']
    text='''# Общий предиктор между числовыми колонками

Это отдельная Python-абляция, не новый production transport и не поддерживаемый
M7 flag. Она использует тот же private day,19882 train/63943 holdout, без
пересечения установок; словари16/32KiB обучены только на новом train выводе.

Универсальная модель рассматривает до16 предыдущих signed-int колонок. Для каждой
позиции берёт значение предыдущей колонки той же строки либо0 при отсутствии
поля. Кодирует разность/сумму через V6 integers; в payload оплачены opcode5/6 и
расстояние1..16. Выбор по минимальному raw размеру включает прежние numeric
режимы0..4. Переполнение исключает кандидат; decoder проверяет opcode, ссылку и
восстановленную int64 область. Ни названий игровых полей, ни правил Puzzle нет.

| Данные | Прежний dict32 | Cross dict16¹ | Cross dict32¹ | Выигрыш dict32 | Python pack+transform100 p50, мс |
|---|---:|---:|---:|---:|---:|
'''
    for r in rows:
        b=r['baseline_B_event']['32768'];c=r['estimated_frame_B_event']['32768']
        text+=f"| {r['variant']} | {b:.3f} | {r['estimated_frame_B_event']['16384']:.3f} | {c:.3f} | {b-c:.3f} | {r['python_base_pack_and_transform100_ms']['p50']:.2f} |\n"
    text+='''
Размер — Б/событие.¹ Измерен реальный новый raw column stream и его zstd payload,
добавлены32B+два varint под прежний header/CRC. Полного кадра с новым flag пока
нет, negotiation/HTTP/native/Unity не реализованы. Поэтому это оценка размера
формата, а не подтверждённый M7 traffic result. Setup,HTTP/ACK/retry исключены.
Original event UUID не сохраняются; `all_clean` предполагает ранее описанную
условную миграцию interaction identity.200 неизвестных событий оплачены full
V1 gzip fallback в каждом варианте. Прежние baseline totals пересчитаны и точно
совпали с tables-benchmark.json для обоих размеров словаря.

Для каждой успешно обработанной пачки выполнен обратный cross decode: все
числа сравнены с исходными полями; восстановленный старый raw stream побайтно
равен исходному. Сжатые данные обоих словарей отдельно декомпрессированы и
сравнены.19 Python tests включают все прежние проверки и три новых: оба знака,
отсутствующий source, расстояние16, неверные opcode/ссылки и int64 overflow,
полные raw bodies с UUID и без, разные shape/field masks.

Улучшение составляет около0.28 Б/событие, целевой порог raw<13/clean<7 всё ещё
не достигнут даже по этой размерной оценке. В текущем Python prototype упаковка
и transform занимают около26мс/100; это дополнительно сканирующий probe, а не
оценка производительности будущего C#. Выбирать его для телефона по этому
эксперименту нельзя. Модель **не включена в основной C#/Unity packer**; старые
Zero-GC/CPU результаты на неё не распространяются. Выбор по этому holdout
exploratory; для независимого подтверждения нужен новый корпус.

Воспроизведение: `run_cross.sh` после `run_tables.sh`. Код:cross7.py,
bench_cross7.py,test_cross7.py. Evidence:results/cross-benchmark.json,
cross-tests.log; private dictionaries не экспортируются. SDK Runtime/ и игра
не менялись. Специфичная для Puzzle очистка остаётся в game_cleanup.py отдельно
от общего алгоритма.
'''
    (ROOT.parent/'08-cross-column-evaluation.md').write_text(text)

if __name__=='__main__':run()
