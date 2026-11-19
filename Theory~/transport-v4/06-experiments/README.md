# Воспроизведение V4

[проверено] Python3.14.8/macOS arm64; requirements.txt совпадает с pinned V3. Все изменения — только исследовательский transport-v4. Ни продукт, ни V2/V3 не переписаны.

Из этой папки:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
PY=.venv/bin/python sh run_all.sh
```

[зависимости] Требуются соседние `../../transport-v2/04-experiments/` и `../../transport-v3/06-experiments/`, включая исходные scripts и V3 dictionaries/results. В handoff evidence.zip они сохранены с исходными относительными путями. Не передавайте только Markdown без кода и dictionary bytes.

[порядок] run_all выполняет внешний аудит → свежий полный V2 run → V3 checks → paired matrix → selection/holdout/resources → extreme → queue → network/fixture → native/header experiments → финальные passes → V4 tests → docs → verifier. Вывод каждого этапа отдельно в results. Сеть нужна для V2 TLS probe и native_build; NDK и libzstd для native этапов. Большие библиотеки не устанавливаются в SDK; временные build/source directories автоматически удаляются.

Native по умолчанию использует Unity NDK6000.3.16f1 и Homebrew libzstd1.5.7. Это документированные пути реально проверенного стенда, не обещание переносимости. При отсутствии среды можно воспроизвести все Python tests/matrix отдельно; native файлы тогда остаются ранее измеренными и новый запуск нельзя объявить полным.

[измерено] В ходе работы все перечисленные этапы запускались отдельно, часть — несколько раз после исправлений. Объединяющий shell wrapper проверяется синтаксически; его полный повтор после составления не выполнялся. Логи и verification связывают фактические запуски с текущими исходниками. CPU сравнивается только в рамках явно указанной среды; тесты Python не подтверждают C#/JNI/Android runtime.

|Команда|Доказательство|
|---|---|
|external_audit.py|Исходные self-tests pass и новые counterexamples в external-audit.json|
|v2-rerun/run_all.sh|Свежий full baseline; v2-fresh-comparison.json сравнивает12 deterministic artifacts|
|test_v3.py изV3|8233 event roundtrip и2000 outer mutations, stdout перенаправлен вV4|
|bench_v4.py|Полная cap/dictionary/format матрица, каждыйV4 кадр decoded+rendered|
|evaluate_final.py|Выбор поvalidation303, затемholdout909/drift808, RAM/CPU/table budget/cadence|
|extreme_v4.py|Парные cap500 варианты, отдельно synthetic Rule1|
|queue_storage.py|SQLite payload/WAL/checkpoint sizes с точным roundtrip|
|native_memory.py|C API CDict/CCtx/DDict sizes иby-reference разница|
|native_build.py|Pinned source → Android ELF sizes+symbols и18host roundtrips|
|network_v4.py|Равнаяcadence H1/H2/H3 модель иполный20event fixture|
|header_experiment.py|Реальный2byte savings trial сfixed-window rebuild|
|memory_floor.py|Дополнительные fast/dict16/64/minimal-table варианты наvalidation303|
|final_passes_v4.py|Ultra22/LDM при тех жеdictionary bytes иvalidation|
|test_v4.py|9 meaningful tests,6000 frame/core mutations,SQLite request/dedup model|
|export_reports.py|Документы изфактических JSON|
|verify.py|SHAimmutability,12fresh reproductions,fixturefull roundtrip,numeric/report consistency|

[границы] Генераторы детерминированы; это не production traffic. verify.py не доказывает глобальную оптимальность, production validation, crash consistency на устройстве или отсутствия bugs. Canonical digest и exact capsule — реальные работающие references; реальный сервер/SDK migration отсутствуют.
