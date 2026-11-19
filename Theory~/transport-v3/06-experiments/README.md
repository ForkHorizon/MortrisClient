# Воспроизведение V3

[измерено] Среда: Python 3.14.8, macOS arm64; zstandard 0.25.0 / C 1.5.7. Все Python зависимости закреплены в requirements.txt. Python 3.11+ предполагается, но матрица версий не проверялась. Это исследовательские скрипты; SDK и сервер не менялись.

Из этой папки:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
PY=.venv/bin/python sh run_all.sh
```

[оценка] Полный запуск занимает несколько минут; медленнее всего Brotli-11 в исходной матрице V2. Сеть нужна для measure_tls.sh внутри копии V2 и native_size.py (Maven AAR). AAR не сохраняется и не устанавливается в продукт. Для запуска без сети выполните этапы ниже отдельно, пропуская эти два шага и явно отмечая пропуск.

[измерено] В этой сессии V2 run_all и остальные этапы запускались отдельно, включая исправления и повторы. Объединяющий run_all.sh сохраняет тот же порядок зависимостей. verify.py проверяет комплектность, JSON, исходные хеши, числовую согласованность и критерий остановки.

## Данные

[код] Исходные модули импортируются из `../../transport-v2/04-experiments` без изменения файлов. `v2-reproduction/` — отдельная полная копия исходных скриптов и результатов; full V2 run пишет туда. audit.json хранит SHA-256 исходных файлов V2, extras.py и verify.py повторно проверяют их неизменность. API credentials и реальные события не использовались.

[измерено] Первый генератор: исходный gen.py, профили base/rich; test seed101 / 6 установок, train seed202 / 18 установок. Второй: alternate.py, те же seeds и число установок, по900 событий. Число test events: 8944 / 7899 / 5400. corpus-manifest.json содержит counts и SHA-256 последовательности `(uint64LE body_length || V1_body)` по исходным границам пачек. `data/{base,rich,alt}-20events.json` — читаемые fixtures; полные корпуса регенерируются.

[код] Alt не использует игровую цепочку из4 событий: 80 редких типов, длинные случайные многоязычные строки, opaque hex160 байт, board600 символов с4 изменениями на событие, смена схемы/версии посередине и размеры пачек1/3/7/25/50/100. Значения входят в текущий SDK-контракт. Китайские ключи проверены отдельно unicode_keys.py и исключены из основных итогов: текущий EventValidator их отвергает.

[оценка] Оба генератора синтетические; rich — профиль того же первого генератора. Совпадение train/test распределений, подбор профиля по двум размерам и выбор параметров на синтетике могут завысить выигрыш. Некоторые дополнительные опыты используют2 test / 8 train установок, arithmetic8 пачек или field arithmetic6 пачек — объём записан в JSON. Seeds не менялись ради результата.

## Эксперименты

У всех Python команд ниже префикс `.venv/bin/python`. В results сохранены сырые числа и логи; подробные выводы — в04-options-comparison.md.

|ID|Вопрос и данные|Команда|Сырой вывод|Ограничение|
|---|---|---|---|---|
|E0|Границы SDK против кодека V2|`audit.py`|`results/audit.json`|Python oracle; реальные Unity bytes отдельно|
|E1|Воспроизведение V2|Из v2-reproduction: `PY=../.venv/bin/python sh run_all.sh`|`v2-reproduction/results/*`, `results/v2-run-all.log`|TLS чужих хостов, desktop CPU|
|E1b|Побайтовое сравнение артефактов|`reproduction_check.py`|`results/reproduction-check.json`|CPU/TLS исключены из byte comparison|
|E2|Компрессоры, OOD-словарь, predictors, размеры пачек, Markov, arithmetic|`bench.py`|`results/bench.log`, `bench.json`, `dict64_*.bin`|Синтетика, нет holdout по реальным версиям|
|E3|Словарь на целевом размере пачки100|`refine.py`|`results/refine.log`, `refine.json`, `dict64_batch100_*.bin`|Те же test events; matched training для всех вариантов|
|E4|Field/current type/previous type arithmetic; history4;3 словаря; integers|`further.py`|`results/further.log`, `further.json`|AC только value stage; bitpack/EF — расчёт raw bytes; history не полноценный сервер|
|E5|Exact replay hash при cap500|`extreme.py`|`results/extreme.log`, `extreme.json`, `dict64_extreme_*.bin`|Алгоритм синтетики, не реальной игры|
|E6|Два финальных прохода дают улучшение>2%?|`final_passes.py`|`results/final-passes.log`, `final-passes.json`|Локальный поиск; если бы predictor приняли, нужен mode descriptor|
|E7|Generic sparse edits строк/снапшотов|`checkpoint.py`|`results/checkpoint.json`|String value stage, без dictionary; не additive с whole frame|
|E8|V3 roundtrip, границы, malformed, mutation fuzz|`test_v3.py`|`results/v3-tests.json`|8233 событий,2000 мутаций outer frame; нет coverage fuzz/Unity oracle|
|E9|Wire budget по cadence и соединениям|`network.py`|`results/network.json`|HPACK encoder измерен; прочее — явная модель, не pcap|
|E10|Весь Python pipeline против compression-only|`cpu_v3.py`|`results/cpu-v3.json`|Desktop, не Android/Unity; decode только внешней рамки|
|E11|Native library cost|`native_size.py`|`results/native-size.json`|Пинованный AAR1.5.7-6, не APK delta|
|E12|Patch словаря,20-event hex, V2 integrity|`extras.py`|`results/extras.json`, `example-*.bin/json`|Patch между синтетическими корпусами, не релизами|
|E13|Хеши полных корпусов и fixtures|`corpus_manifest.py`|`results/corpus-manifest.json`, `data/*.json`|V1 synthetic conventions, не wire capture|
|E14|Другой язык ключей|`unicode_keys.py`|`results/unicode-keys.json`|Отдельная sensitivity вне текущего SDK-контракта|

[код] Внешняя рамка: frame.py. Выбор безопасного MTB2-подмножества: codec.py. Arithmetic reference и самостоятельная проверка: `models.py`. Полный roundtrip kind2: extreme.py + codec.restore. frame.unpack не валидирует все поля распакованного MTB2; будущий сервер обязан выполнить более строгую спецификацию03.

## CPU и отрицательные результаты

[измерено] bench.py считает байты C-библиотек; создание Python compressor входит в timing. cpu_v3.py включает encode→decode→serialize verification и выбор из4 compressors: p50≈3,6/4,7/5,2мс, p95≈4,4/5,8/10,2мс для base/rich/alt. Outer decode≈11–32мкс, без полного разбора payload. Эти цифры не подтверждают Android<1мс. arm64 AAR `.so`:603960 байт raw /261876 ZIP; дополнительно64KiB dictionary и память CDict. Батарея не измерена.

[измерено] В логах сохранены отрицательные результаты: arithmetic, linear/per-type после matched training, XOR, prefix, sparse edits, несколько словарей, ultra/LDM. PPMd whole-install не является Shannon floor. Настоящие cmix/PAQ, FSST, Chimp/Elf и ANS backend не запускались; для них в04 приведены оценки и открытые вопросы, без выдуманных benchmarks.

[измерено] Разработка выявила два полезных сбоя: слишком малый max_window_size отвергал обычные пачки; повреждённый zstd content-size вызывал MemoryError до preflight header check. Исправления исследовательской рамки подтверждены тестами; продуктовый код не исправлялся.
