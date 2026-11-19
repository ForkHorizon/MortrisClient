# Независимый аудит нового исследователя

[источник] `review-input/REPORT.md` — входные данные, не распоряжения по реализации. Оригинальный код/результаты сохранены отдельно; рабочая копия меняет только путь common.EXP для воспроизведения. Готовые Linux executables не запускались.

| Утверждение | Вердикт | Доказательство / поправка |
|---|---|---|
| V4 baseline | Подтверждено | Все 13 baseline rows воспроизвелись, включая cap500 и drift. |
| Dynamic MTB5 body | Подтверждено на данных | Ещё 36 строк body/condition/no-prior воспроизвелись; вместе 49. Numeric sizes, не CPU timing или compressed pickle bytes. |
| Session reset / wire | Подтверждено в исходной модели | Оба JSON результата совпали целиком. Это идеальная ACK/cache модель и explicit network assumptions, не pcap. |
| Fixed table64/256/1024KiB | Только within-process | fixed_table.py использует hash(ctx). PYTHONHASHSEED меняет slot и frame; новый run с seed0 приложен, но exact старые числа без seed воспроизвести нельзя. |
| 64KiB памяти | Неполная метрика | Только 2×uint16×16K counters. Дополнительно нужны prior, tables/tidx,last,EMA, buffers и lookup/hash state. Нативный rcbench имеет 512KiB slots+prior, не 64KiB всего. |
| zstd CCtx+CDict | Ошибка суммирования | V4 предупреждал: Python CCtx и отдельный stable C API CDict/CCtx — разные способы/параметры. Нельзя просто прибавить 1,65MB к Python CCtx и объявить это измерением. |
| CPU дешевле zstd19 | Не доказано для кодека | C replay исключает field predictors, strings, source serialization и context serialization/hash. Stateful timing использует статический trace, не полный stateful encoder. |
| C-бенч на alt204us | Артефакт реализации | get() использует>>49 независимо от SLOTS: начальные bucket лишь 32768 даже при 131072 slots. Длинные цепочки и отсутствие full-table guard нельзя переносить в client performance. |
| Приор/порт | Частично спроектировано | Python pickle не является portable wire format. Float EMA с/4 и*0.9 требует точных правил округления; отчёт сам признаёт отсутствие битовой совместимости при переносе. |
| sent_at | Дефект | code_batch читает signed delta, затем выбрасывает. Контрпример 9999 декодируется как+250 и CRC всё равно проходит: CRC считается старым renderer. |
| reset_batch_state | Дефект | L=m.last берётся до замены m.last. После stateless encode model не содержит ожидаемого ev-state. Исправлено до использования candidate snapshots. |
| CRC ловит всё | Слишком сильный вывод | 2000 random mutations действительно отклонены. Но добавление 1/64 нулевых байт перед CRC принимается, а CRC не аутентифицирует state/model. |
| state token | Дефект/незавершённый протокол | Всегда 0, decoder его не читает:255 принимается. При failedCRC decoder уже изменил переданный live model. |
| Восстановить state из JSON событий | Не доказано, обычно недостаточно | JSON может потерять original int/float/Decimal tag; overlay и byte coding decisions также влияют на model. Нужен полный typed snapshot/оригинальный codec transcript либо stateless fallback. |
| 11B entropy floor | Условная эвристика | Оценка зависит от выбранной факторизации и запрета game rule. Не Shannon floor источника: hash детерминирован. Уже известный rule1 даёт гораздо меньше без потерь. |
| Убрать placed_state_hash | Только при exact reconstruction | Нельзя просто удалить данные. В V5 есть отдельный проверяемый rule flag; основная таблица без него. Реальный алгоритм игры неизвестен. |
| Сразу заменить SDK | Пока рано | Сеть улучшена, но нет полного native/C#/Go pipeline, device CPU/RSS, production distribution и migration integration. V5 — новый проверенный исследовательский кандидат. |

## Проверки контрпримеров

[измерено] `submission-counterexamples.json`: лишние нули принимаются, token255 принимается, failedCRC меняет live state, sent_delta9999 теряется. `submission-hashseed.json` показывает различные frames при hashseed0/1/2. Исходные 300 fuzz-batches и 2000 random mutations при этом проходят — значит, они не покрывали эти случаи.

[вывод] Полезная идея подтверждена: model по роли/полю/контексту уменьшает поток сильнее V4 byte compressor на этой синтетике. Но исходный stateful prototype и цифры всей памяти/CPU не являются готовым SDK. V5 ниже — исправленный более ограниченный вариант; его таблицы не подменяют измерения автора задним числом.
