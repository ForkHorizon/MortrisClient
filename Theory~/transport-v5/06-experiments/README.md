# Воспроизведение Transport V5

Проверенная среда: Python3.14.8, macOS arm64, зависимости из requirements.txt (совпадают сV4), clang для независимого C entropy test. На других ОС native_check требует обычной адаптации команды сборки shared library; сама Python матрица отдельно запускается без неё.

Из этой папки:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
PY=.venv/bin/python sh run_all.sh
```

Нужны соседние `../../transport-v2`, `../../transport-v3`, `../../transport-v4`, включая scripts/results/dictionaries. Полный evidence.zip сохраняет исходный layout и все входные SHA. Только Markdown не позволяет воспроизвести исследование.

В этой работе этапы запускались отдельно и повторялись после исправлений. Полный объединяющий run_all.sh составлен после измерений и проверен синтаксически; его повтор целиком не заявлен. Все фактические логи сохранены. Скрипты не посылают события на внешний сервер; recovery SQLite создаётся во временных файлах/памяти. Никакой SDK или предыдущая версия не переписывается.

|Этап|Команда|Доказательство|
|---|---|---|
|Входная работа|submission-rerun/baseline_v4.py,run_matrix.py,session_reset.py,wire_eval.py|49 numeric body rows и2 JSON полностью воспроизведены|
|Авторские тесты|submission-rerun/test_roundtrip.py,test_mutation.py|300 randomized batches и2000 мутаций проходят, но не покрывают найденные дефекты|
|Нестабильныйhash|hashseed_audit.py;fixed_table.py сPYTHONHASHSEED=0|Разные salted frames; новые fixed-table числа не выдаются за точную копию старых|
|ПриорыV5|probe_v5.py base/rich/alt/drift|Собственное train202,14bit bounded probability table,typed raw prior иcompressed asset|
|Новые данные|bench_v5.py profile|historical/validation/fresh1729+drift1733; stateless/stateful/session/deadline; full exact verification|
|Память|memory_v5.py,compact_prior.py|Полные Python models/копии/cache иотдельная ценаEMA наvalidation|
|Сеть|network_v5.py|Warm/cold H1/H2/H3 появной модели,ACK2/18B|
|Восстановление|test_recovery.py,miss_cost.py|LostACK,restart,cachemiss,late/wrongACK,conflict,origin authorization,actual failed-request bytes|
|Типы/границы|test_v5.py,extra_tests.py|15 test methods суммарно сrecovery; source/schema/CRC/canonical/prior/deadline/state cases|
|Новаямутация|mutation_v5.py|2000 altered/truncated/extendedframes,prior immutable|
|C stage|native_check.py|36 batches: entropybytes+finalprobabilities совпадают,stage-onlytiming|
|Fixtures|fixtures.py,asset_manifest.py,corpus_manifest.py|Полныеframes/source/modelSHA/cross-processhashseed/corpusSHA|
|Публикация|export_reports.py,verify.py|ЧислаизrawJSON,целостностьвходов,комплектностьиregression disclosure|

Рекомендуемый кандидат этого раунда — V5 stateless. Stateful остаётся экспериментальным профилем сявнымstate reference/ACK/recovery. Никакая таблица в64KiB не объявляется полной памятью приложения. C benchmark не является полным C#/Go/ARM SDK. Protocol/capture/production gates перечислены в09-open-questions.md.
