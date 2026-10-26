# Воспроизведение Transport V6

Исследовательский стенд, не Unity SDK. Python reference аллоцирует память; нативное C-ядро относится только к integer column packing.

Из этой папки:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PY=.venv/bin/python sh run_all.sh
```

Нужны соседние неизменённые каталоги `transport-v2/04-experiments`, `transport-v3/06-experiments`, `transport-v4/06-experiments`, `transport-v5/06-experiments`, включая сохранённые V5 приоры и manifests. Скрипты импортируют их read-only; результаты пишутся только в этот `results/`. Это не автономный архив со скопированными предыдущими исследованиями. SHA219 используемых исходных/результирующих файлов зафиксированы в `results/input-sha256.json`; verify проверяет их неизменность. Этот manifest фиксирован вручную перед завершающими прогонами и не обновляется run_all автоматически.

Проверенная среда: Python3.14.8, macOS arm64, clang, zstandard0.25.0/native zstd1.5.7, liblz4 1.10.0. `native_check.py` требует clang и доступные системные libzstd/liblz4 через ctypes.util.find_library. Никакие библиотеки/SDK автоматически не устанавливаются и данные на сервер не отправляются. `requirements.txt` сохранён совместимым с предыдущим research environment; не означает новые runtime dependencies SDK.

Этапы:

| Скрипт | Что проверяет |
|---|---|
| test_v6.py | 12 тестов: все профили, строгие типы/UUID, unknown schemas, signed zero, exact fixed point, source escape, masks, epoch/restart/auth, LZ4, 1000 damaged frames |
| bench.py | train202; test101/drift808 + holdout1729/drift1733; 11 V6 вариантов, полные независимые V4/V5 encode/decode, source SHA и суммы bytes |
| schema_tools.py | binary build/store table, event IDs, masks, field types, digest roundtrip |
| native_check.py | 1006 C/Python integer cases, capacity failures, allocator-symbol check, prepared-buffer zstd/LZ4 stage timings |
| confirm.py | новый seed2601 без обучения; caps1/7/100, реальные setup bytes, strict IDs и conditional replay |
| fixtures.py | 8 переносимых полных V1 source/frame fixtures с фиксированным epoch |
| field_costs.py | разложение raw columns по полям; сумма точно равна encode_raw |
| export_reports.py | пять Markdown-отчётов из сырых JSON |
| verify.py | input SHA, корпуса/суммы, схемы, fixtures под другим PYTHONHASHSEED, комплектность |

`results/bench.log`, `tests.log`, `native.log`, `confirmation.log`, `run-all.log` сохраняют фактические запуски. `iteration1.log` — ранний дизайн без окончательного epoch/fixed-point; это история эксперимента, не финальные числа. Первый объединённый запуск дошёл до ещё не созданного exporter и завершился с ошибкой; затем exporter/verify были добавлены и весь скрипт повторён. Финальное состояние определяется verification.json и финальным run-all.log.

Бинарный shared library строится локально, не является переносимым артефактом и исключён `.gitignore`. Все fixtures синтетические. Для исходного V1 без потерь используйте `preserve_ids=True`; основной historical comparator исключает event_id так же, как V4/V5. Нельзя выдавать эти два контракта за один.

За границей доказательств: полный нативный encoder/Go decoder, live handshake/DB, Android/iPhone, IL2CPP/Burst, SDK GC и расход батареи. План измерений и память приведены в `../03-cpu-and-battery-evaluation.md`.
