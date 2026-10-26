# Строковые таблицы и остаточная стоимость колонок

Продолжение исследования V7 на том же разбиении:19882 train,63943 holdout,
без пересечения установок. Словари16/32KiB обучены только на train в соответствующем
представлении. Каждый закодированный frame декодирован и сравнён по всем typed
values; неизвестные схемы оплачены полным V1 gzip fallback. Все варианты используют
integer model из предыдущего эксперимента.

| Данные | Модель | dict16, Б/событие | dict32 | full event UUID dict16 | Fallback events | Shapes |
|---|---|---:|---:|---:|---:|---:|
| all_clean | strings | 9.136 | 9.058 | — | 200 | 22 |
| all_clean | metadata | 9.826 | 9.728 | — | 200 | 22 |
| all_clean | combined | 9.286 | 9.216 | 26.091 | 200 | 22 |
| all_clean | logical_strings | 9.154 | 9.062 | 25.934 | 200 | 22 |
| raw | combined | 17.737 | 17.568 | 34.202 | 200 | 22 |
| raw | logical_strings | 17.506 | 17.426 | 33.956 | 200 | 19 |

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
строки. String flag4 теперь портирован в C#/Go; metadata flag16 остаётся только
экспериментом Python. Размерный benchmark рассчитан Python; отдельные
native/Unity проверки приведены ниже. Поле CSharp_Go_Unity в размерном JSON
ссылается на эти отдельные доказательства, а не объявляет весь набор переносимым. Python host CPU приведён в JSON отдельно.

## Диагностическое удаление информации

`profile_remaining7.py` заменяет одну колонку константой и повторно сжимает тем же
numeric словарём. Это поиск остаточной стоимости, **не lossless codec** и не
достигнутая экономия. Эффекты разных колонок не складываются.

| Колонка | Raw Б/событие | Уменьшение при подмене константой, Б/событие |
|---|---:|---:|
| placed_block_ids | 9.463 | 1.115 |
| inventory_group_id | 1.103 | 0.684 |
| release_y_milli | 0.530 | 0.454 |
| block_id | 0.530 | 0.449 |
| release_x_milli | 0.521 | 0.447 |
| active_elapsed_ms | 0.823 | 0.408 |
| nearest_target_distance_milli | 0.410 | 0.314 |
| attempt_id | 0.404 | 0.300 |

Значения не удалялись в результатах lossless benchmark. Проектные имена есть
только в диагностике/отчёте, не в универсальных string7.py/metadata7.py.

Воспроизведение: `06-experiments/run_tables.sh` после исходного и numeric runs.
Итоги: `results/tables-benchmark.json`, `remaining-column-costs.json`,
`tables-tests.log`; точные private dictionaries остаются локально.

## Перенос string model в C# и Go

Preallocated C# packer выбирает те же пять режимов без игровых строк. UTF-8
workspace16KiB и дополнительные500-element arrays выделяются до измерения.
Четыре fixtures независимо декодированы Python и Go; raw C# побайтно совпадает
с Python. Все opcodes0..4 принудительно покрыты; invalid refs/UTF-8/count/tag
отбрасываются Go decoder в отдельных тестах. Native boundary ожидает корректный
UTF-8; lone-surrogate Python experiment не заявлен как переносимый Unity input.

| Fixture | События | .NET mean ms | GC bytes /1000 packs |
|---|---:|---:|---:|
| table-modes100 | 100 | 0.1952 | 0 |
| table-unicode500 | 500 | 0.9699 | 0 |
| table-real-raw | 100 | 0.4027 | 0 |
| table-real-all_clean | 100 | 0.3906 | 0 |

Это pack+reused native zstd; загрузка DTO/каталога, framing/CRC/JNI/HTTP исключены.
Fixtures сохраняют original event UUID; их отдельные compressed_bytes не равны
aggregate legacy-ID результату таблицы выше. Доказательства: native-tables.json,
go-check-tables.json, go-table-tests.log. Воспроизведение: run_native_tables.sh.

Все16 fixtures также прошли Unity Editor Mono и Android ARM64 Development
IL2CPP на4KB/16KB: по1000 упаковок, calibrated0 GC.Alloc, все raw buffers
совпали. Четыре новые string-model fixtures проверены явно; полный pipeline,
physical phone/FPS/thermal не проверены. [Unity evidence](06-unity-runtime-validation.md).
