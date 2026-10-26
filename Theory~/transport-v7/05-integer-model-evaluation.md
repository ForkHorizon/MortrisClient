# Дополнительная generic integer model

Это продолжение V7 после исходного columnar+dictionary benchmark. Старые totals
сохранены как baseline. Цель — уменьшить остаточную избыточность числовых колонок
универсальным алгоритмом, без игровых имён в codec.

На том же дне и том же разбиении по установкам:19882 train,63943 holdout,
по 600 первых событий на установку. Оба размера словаря заданы заранее,
словари обучены только на train в новом представлении.200 событий с неизвестной
схемой по-прежнему оплачены full V1 gzip fallback. Identity contract для legacy
колонок исключает original event UUID; full-ID колонка оплачивает его полностью.

| Вариант | V7 baseline dict32 | Integer model dict16 | Integer model dict32 | Integer model full UUID dict16 |
|---|---:|---:|---:|---:|
| raw | 19.114 | 18.161 | 17.998 | 34.486 |
| all_clean | 10.613 | 9.667 | 9.553 | 26.368 |

Единица — Б/событие, весь frame и CRC включены, setup/HTTP/retry исключены.
Каждый успешно закодированный batch декодирован и сравнён по всем typed values.
Критерии raw<13 и clean<7 всё ещё не выполнены. Эта модель не удаляет SHA или
GUID: game cleanup остаётся отдельным условным преобразованием.

## Формат и проверка

С flag2 signed-int property column получает opcode0..4: исходный V6 packer,
разность с timestamp/sequence/session_elapsed_ms либо integer dictionary+indices.
Самый короткий raw кандидат выбирается до zstd с оплаченным opcode. Переполнение
исключает кандидат; decoder отбрасывает invalid opcode/index/range. Поля кадра,
UUID и остальные типы остаются прежними. Дополнительная программа не переносит
игровые правила в SDK и не обучается на значениях holdout.

В probe несжатая экономия составила 2.460 Б/событие. Наиболее заметны active_elapsed_ms
и event counters; эти имена есть только в диагностике и проектных данных.
Экономию raw нельзя целиком переносить на результат zstd: часть паттернов уже
сжимал старый компрессор. Фактический эффект приведён выше.

Новый C# packer использует preallocated scratch arrays и integer dictionary.
Шесть fixtures: synthetic100, edge int64/uint64/signed-zero/Unicode/Decimal,
500 rows, специальная 500-row проверка всех opcodes, actual raw100 и clean100.
Все прошли независимый Go decoder и Python roundtrip, по 1000 pack+native-zstd
повторений на .NET/macOS с 0 managed GC bytes. Original/default режим также
повторно проверен. Статическая netstandard2.1 библиотека компилируется.

C# candidate-real-raw: 0.400 мс/100 событий, 0 GC bytes на 1000 повторений.

C# candidate-real-all_clean: 0.392 мс/100 событий, 0 GC bytes на 1000 повторений.

Это host typed-column stage, не Unity/IL2CPP и не телефон; framing/CRC/ingress/JNI/HTTP
в замер не входят. Полный Python encode100 p50 примерно 7 мс, а первоначальный
вариант был около 2–3 мс. Дополнительные кандидаты имеют цену CPU: быстрее на
телефоне они не объявлены. Нагрев/энергия и production integration не проверены.

Воспроизведение: `06-experiments/run_numeric.sh`. Основные доказательства:
`results/numeric-benchmark.json`, `native-numeric.json`, `go-check-numeric.json`,
`numeric-tests.log`. Полный generic codec —transport7.py/numeric7.py; C# —native/Columns.cs,
Go —go/main.go. Эта работа продвинула размер и сохраняет host Zero-GC, но не
закрывает исходные критерии V7.
