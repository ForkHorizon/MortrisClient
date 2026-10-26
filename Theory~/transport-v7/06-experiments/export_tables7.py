"""Report experimental table models without promoting Python timing to Unity proof."""
import json
from support7 import ROOT

def run():
    rows=json.loads((ROOT/'results/tables-benchmark.json').read_text())
    assert len(rows)==6 and all(r['events']==63943 for r in rows)
    text='''# Строковые таблицы и остаточная стоимость колонок

Продолжение исследования V7 на том же разбиении:19882 train,63943 holdout,
без пересечения установок. Словари16/32KiB обучены только на train в соответствующем
представлении. Каждый закодированный frame декодирован и сравнён по всем typed
values; неизвестные схемы оплачены полным V1 gzip fallback. Все варианты используют
integer model из предыдущего эксперимента.

| Данные | Модель | dict16, Б/событие | dict32 | full event UUID dict16 | Fallback events | Shapes |
|---|---|---:|---:|---:|---:|---:|
'''
    for row in rows:
        b=row['B_event'];full=f"{b['full_ids_dict16']:.3f}"if 'full_ids_dict16'in b else '—'
        text+=f"| {row['variant']} | {row['model']} | {b['dict16']:.3f} | {b['dict32']:.3f} | {full} | {row['fallback_events']} | {row['catalog_shapes']} |\n"
    text+='''
Оплачены header/CRC и fallback; setup, HTTP/TLS/ACK/retry исключены. Legacy колонки
не сохраняют original event UUID: нужна отдельная миграция immutable origin+sequence.
`all_clean` дополнительно предполагает безопасную миграцию interaction identity,
которой пока нет в production. Нельзя сравнивать эти числа с full-ID как идентичный
контракт доставки. Порог raw<13/clean<7 по-прежнему не выполнен.

`strings` (flag4) выбирает самый короткий полностью оплаченный raw payload:
исходная distinct UTF-8 таблица; prefix+suffix относительно предыдущего уникального
значения; binary UUID/hex; смешанная таблица с tag для каждого значения. Только
канонические lowercase UUID/hex получают binary tag: регистр, пробелы, Unicode и
Decimal lexemes сохраняются точно. Префиксы задаются в байтах; восстанавливаются
до UTF-8 decode. Это общий алгоритм без CSV-разбора и игровых ключей.

`metadata` (flag16) пробует таблицы distinct values/deltas для пяти служебных
integer streams. На очищенных данных он не дал улучшения относительно numeric baseline
9.553 Б/событие и не включён в рекомендуемый кандидат.

`logical_strings` оставляет в каталоге один тип string независимо от содержимого
значения. Формат UUID/hex выбирается внутри колонки, а не создаёт отдельный shape.
Политика записана в descriptor и меняет catalog ID; прежние каталоги/кадры не
меняются. Отсутствующее поле и настоящий другой примитивный тип по-прежнему
требуют известного shape или полного fallback. Каталог не дообучается на holdout.
В этом корпусе string policy не уменьшила200 fallback events; на очищенных
данных размер не улучшился относительно `strings`. Гипотеза о причине fallback
не подтвердилась, хотя каталог сырых данных стал меньше.

Выбор лучшего варианта сделан после просмотра этого holdout: это exploratory
сравнение, не независимая подтверждающая оценка выбранного победителя. Для такого
подтверждения нужен отдельный день/набор установок.16 тестов проверяют старый
протокол и новые модели, включая integer overflow, неверные ссылки и смешанные
строки. Новые string/metadata opcodes **не портированы в C#/Go/Unity**. Старые
Unity Zero-GC результаты относятся к baseline/numeric stage; переносить их на
эти дополнительные модели нельзя. Python host CPU приведён в JSON отдельно.

## Диагностическое удаление информации

`profile_remaining7.py` заменяет одну колонку константой и повторно сжимает тем же
numeric словарём. Это поиск остаточной стоимости, **не lossless codec** и не
достигнутая экономия. Эффекты разных колонок не складываются.

| Колонка | Raw Б/событие | Уменьшение при подмене константой, Б/событие |
|---|---:|---:|
'''
    costs=json.loads((ROOT/'results/remaining-column-costs.json').read_text())
    for row in costs['fields'][:8]:text+=f"| {row['field']} | {row['raw_B_event']:.3f} | {row['marginal_B_event']:.3f} |\n"
    text+='''
Значения не удалялись в результатах lossless benchmark. Проектные имена есть
только в диагностике/отчёте, не в универсальных string7.py/metadata7.py.

Воспроизведение: `06-experiments/run_tables.sh` после исходного и numeric runs.
Итоги: `results/tables-benchmark.json`, `remaining-column-costs.json`,
`tables-tests.log`; точные private dictionaries остаются локально.
'''
    port='Они пока не портированы в C#/Go/Unity'
    if (ROOT/'results/native-tables.json').exists():
        native=json.loads((ROOT/'results/native-tables.json').read_text())
        independent=json.loads((ROOT/'results/go-check-tables.json').read_text())
        assert len(native)==len(independent)==4 and all(r['gc_bytes']==0 and r['python_raw_parity']and r['python_roundtrip']for r in native)
        assert all(r['go_column_parity']for r in independent)
        text=text.replace('Новые string/metadata opcodes **не портированы в C#/Go/Unity**. Старые\nUnity Zero-GC результаты относятся к baseline/numeric stage; переносить их на\nэти дополнительные модели нельзя.', 'String flag4 теперь портирован в C#/Go; metadata flag16 остаётся только\nэкспериментом Python. Размерный benchmark рассчитан Python; отдельные\nnative/Unity проверки приведены ниже. Поле CSharp_Go_Unity в размерном JSON\nссылается на эти отдельные доказательства, а не объявляет весь набор переносимым.')
        text+='\n## Перенос string model в C# и Go\n\nPreallocated C# packer выбирает те же пять режимов без игровых строк. UTF-8\nworkspace16KiB и дополнительные500-element arrays выделяются до измерения.\nЧетыре fixtures независимо декодированы Python и Go; raw C# побайтно совпадает\nс Python. Все opcodes0..4 принудительно покрыты; invalid refs/UTF-8/count/tag\nотбрасываются Go decoder в отдельных тестах. Native boundary ожидает корректный\nUTF-8; lone-surrogate Python experiment не заявлен как переносимый Unity input.\n\n| Fixture | События | .NET mean ms | GC bytes /1000 packs |\n|---|---:|---:|---:|\n'
        for row in native:text+=f"| {row['fixture']} | {row['events']} | {row['mean_ms']:.4f} | {row['gc_bytes']} |\n"
        text+='\nЭто pack+reused native zstd; загрузка DTO/каталога, framing/CRC/JNI/HTTP исключены.\nFixtures сохраняют original event UUID; их отдельные compressed_bytes не равны\naggregate legacy-ID результату таблицы выше. Доказательства: native-tables.json,\ngo-check-tables.json, go-table-tests.log. Воспроизведение: run_native_tables.sh.\n'
        port='String model портирована в C#/Go с 0 GC на host; metadata model не портирована'
        names=('unity-editor','unity-android','unity-android-16k')
        if all((ROOT/'results'/f'{name}.json').exists()for name in names):
            reports=[json.loads((ROOT/'results'/f'{name}.json').read_text())for name in names]
            if all(sum(bool(x.get('string_model'))for x in r['measurements'])==4 for r in reports):
                assert all(x['gc_alloc_samples']==0 and x['raw_parity']for r in reports for x in r['measurements'])
                text+='\nВсе16 fixtures также прошли Unity Editor Mono и Android ARM64 Development\nIL2CPP на4KB/16KB: по1000 упаковок, calibrated0 GC.Alloc, все raw buffers\nсовпали. Четыре новые string-model fixtures проверены явно; полный pipeline,\nphysical phone/FPS/thermal не проверены. [Unity evidence](06-unity-runtime-validation.md).\n'
                port='String model прошла C#/Python/Go и Unity Mono/Android IL2CPP с 0 GC на проверенном этапе; metadata model не портирована'
    (ROOT.parent/'07-string-table-evaluation.md').write_text(text)
    best=min((r for r in rows if r['variant']=='all_clean'),key=lambda r:r['B_event']['dict32'])
    raw=min(r['B_event']['dict32']for r in rows if r['variant']=='raw')
    return f"\nДополнительные модели строк/каталога дали лучшие exploratory результаты **{raw:.2f} Б/событие** на исходных и **{best['B_event']['dict32']:.2f} Б** на условно очищенных данных, без исходных event UUID. {port}; исходные цели не закрыты. [Строковые таблицы и ограничения](07-string-table-evaluation.md).\n"

if __name__=='__main__':print(run())
