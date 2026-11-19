# Порядок возможного внедрения

[статус] Этот пакет ничего не выкатывает в продукт. Следующие пункты — требования к отдельному внедрению, не утверждение об их выполнении.

1. Сначала снять Unity/.NET→JSONObject→SQLite→V1 byte oracle на реальных устройствах. Зафиксировать канонизацию numeric lexemes/UTF16 escapes и миграцию event_id↔origin/sequence. Включить lossless shadow roundtrip без изменения отправки.
2. Измерить существующий V3/MTB2 low-memory zstd profile на тех же событиях, включая CPU/p99/peak RSS/APK delta. Если он удовлетворяет целям RAM, это самый простой вариант: перенос нового core необязателен.
3. Сравнить V4 trailer и simple legacy shape на реальном holdout нескольких релизов; предзадать допустимую регрессию сети/CPU. Короткие сессии, редкие события и explicit Flush — самостоятельные strata, а не cap100 склейка.
4. Только после server auth/dedup/limit implementations: небольшой negotiated canary, kill switch, dict fallback, literal/V1 retry, no-delete on malformed ACK. Immutable row binding и closed request callbacks обязательны. Старые dict IDs обслуживаются до закрытия retry horizon.
5. Native wrapper переносится в Unity/JNI с ABI tests, error-path allocation/free tests, thread ownership, symbol/size checks и проверкой Android ELF runtime. Fast-only mode не подменяет полную level15/19 библиотеку.
6. Queue compression — отдельная миграция. Сначала per-row reversible вариант с dual-read и checksum/format version; crash/reopen/disk-full/partial-ACK/quarantine/reset tests. Chunked blobs пока исследование; они не нужны для сетевого V4.
7. Game rule включать только после source audit реальной игры и exact shadow prediction; mismatches уходят literal, не вычисленным значением. СинтетическийSHA rule не становится продуктовым только потому, что он сжалbase.
8. Server cache ограничить byte-budget/LRU; per-origin watermark ускоряет lookup, но durable per-event conflict evidence не удаляется по размеру batch. Измерить cold duplicate lookup IOPS, retention и restore/clone recovery.

[оценка] Go/No-Go задаётся владельцем продукта по фактическим SLO и новым данным. Порог15% hash misses или3.5ms из ответа агента не выводится из имеющихся измерений; их нельзя объявлять универсальными release gates. Оптимум по RAM, CPU и сети — разные точки.
