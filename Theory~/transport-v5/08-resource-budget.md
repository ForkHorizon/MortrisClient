# Полная стоимость памяти, модели и CPU

[измерено] Все значения вбайтах; вероятность — только одна структура. Не складывать несовместимые измерения Python/C API, не считать 64KiB таблицы всей памятью клиента.

| Корпус | Probability table | Decoded prior snapshot | Compressed asset | Prior Python graph | One post-state graph | Encode-only cold extra peak |
|---|---|---|---|---|---|---|
| base | 65536 | 155965 | 33998 | 490728 | 527472 | 2086151 |
| rich | 65536 | 196676 | 50671 | 662177 | 710667 | 2543874 |
| alt | 65536 | 219587 | 72551 | 1032580 | 1048359 | 3972566 |
| drift | 65536 | 102655 | 26703 | 260443 | 264965 | 735458 |

[метод] sys.getsizeof recursive graph считает retained Python model, включая probs/tables/tidx/EMA/last; это не C#/IL2CPP layout. Tracemalloc extra peak начинается после загрузки prior и не включает его; включает mutable candidate, выход и coldcontext cache. Cache ограничен 32768 entries, но он тоже занимает память. Отдельные encode+decode peaks в memory.json включают одновременно клиентский и серверный candidate, их нельзя называть client-only peak. Строки/objects logical input заранее построены генератором, реальный SQLite/JNI/JSON input parsing не входит.

[код] Stateless нужны immutable prior и mutable рабочаякопия; только probability buffers уже могут требовать 2×65536 Б. Clone/string lookup/EMA могут выделять память. Source raw table — не mmap-ready готовый CDict, и model prior — не бесплатный 64KiB. V4 low-memory profile65–159k CCtx остаётся отдельной сильной точкой; нет доказательства, что новый целый клиент использует меньше RAM.

## Упрощение prior без смены основной модели

[измерено] Только validation303, не переопределение primary по fresh holdout. Если убрать обученные EMA иадаптировать их внутри запроса, asset и decoded snapshot уменьшаются, тело немного растёт:

| Корпус | Full asset | No-EMA asset | Full Б/соб. | No-EMA Б/соб. | No-EMA snapshot |
|---|---|---|---|---|---|
| base | 33998 | 29045 | 13.341 | 13.478 | 78105 |
| rich | 50671 | 44373 | 31.871 | 32.023 | 86450 |
| alt | 72551 | 66322 | 120.880 | 120.946 | 123992 |
| drift | 26703 | 26270 | 26.513 | 26.875 | 98220 |

[ограничение] Даже alt no-EMA asset66322 Б немного больше 64KiB. Для APK/update budget сравнивать compressed assets одинаковым упаковщиком; для RAM — decoded модели+copies. Отказ от zstd .so возможен только после полного managed-port инадёжного V1 fallback; исследовательские Python helpers и C entropy test не доказывают APK delta.

## CPU: что действительно измерено

| Корпус | Python full p50 ms/batch | p95 | C entropy μs/event |
|---|---|---|---|
| base | 65.854 | 68.977 | 0.455 |
| rich | 122.618 | 129.275 | 1.109 |
| alt | 218.689 | 224.378 | 3.019 |
| drift | 3.284 | 8.691 | — |

[измерено] Python pipeline = encode+bounded/canonical decode+source checks+byte equality,12 первых fresh batches, input уже logical events. Это host timing, часть прогонов делила CPU с другими экспериментами; не phone budget и не доказательство ускорения. V4 вызывает C zstd, новый field codec написан на Python, поэтому сравнение этих языков не предсказывает C# порт.

[измерено] Новый независимый C entropy engine совпал с Python по output bytes **и final probability counters** на 36 пачках,3600 событиях; 7 повторов накаждойпачке. Входные context indices предварительно вычислены. Timing не включает BLAKE2s/context serialization/lookup, predictor search/EMA, строковые таблицы,JSON/CRC/framing или ACK. Поэтому выражение«весь MTB5 дешевле zstd19» пока не доказано.

[риск] BLAKE2s накаждыйконтекст и O(properties²) partner statistics требуют настоящего native/managed benchmark. C# UInt128 вцелевой Unity среде нельзя предполагать: residuals до 70 бит требуют точно описанной multiword арифметики/escape, а HEX надо стримить по bytes, не выделять BigInteger накаждыйбит. Никаких«300 строк безаллокаций» этот Python reference не обещает.
