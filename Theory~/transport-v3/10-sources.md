# Источники и границы

[код] Локальные первичные источники: `../transport-v2/{00-summary.md,05-review-guide.md,03-ablation.md,01-protocol-spec.md,02-options-comparison.md,07-open-questions.md}`, все `../transport-v2/04-experiments/*.py`, контекст `../event-transport-optimization.md`. V2 сохранён неизменным; SHA-256: `06-experiments/results/audit.json`, повторная проверка `extras.json`.

[код] SDK: `Runtime/Internal/AnalyticsUploader.cs:191–232` (реальный sent_at, HttpClient, Fastest), `:301` и `:451` (ack UUID); `PersistenceEventSerializer.cs` (CLR числа, строки, порядок); `EventValidator.cs` (32 свойства, ASCII snake_case 64, string1024, свойства8KiB, все конечные double); `Native~/android/analytics/src/main/java/com/daliys/analytics/AnalyticsQueue.java:39,52–65,177–191` (noBackup, reset, sequence, JSONObject). Карта Graphify подтверждает эти связи; память проекта о «будущем U2» устарела, код при аудите приоритетнее карты.

Проверены онлайн 2026-10-16; ниже спецификации/авторские реализации, без пересказов сторонних блогов.

- [источник] [RFC 8878 — Zstandard](https://www.rfc-editor.org/rfc/rfc8878.html): framing, dictionary, window. [RFC 9659](https://www.rfc-editor.org/info/rfc9659/): ограничение window для HTTP. Стандарт не обеспечивает доставку/версионирование словаря сам.
- [источник] [Zstd manual](https://facebook.github.io/zstd/zstd_manual.html) и [CLI options](https://github.com/facebook/zstd/blob/dev/programs/zstd.1.md): advanced params, LDM, уровни ultra. Версия C в эксперименте 1.5.7, не вывод о всех версиях.
- [источник] [zstd-jni](https://github.com/luben/zstd-jni): Android AAR и JNI. [Пинованный AAR 1.5.7-6](https://repo.maven.apache.org/maven2/com/github/luben/zstd-jni/1.5.7-6/zstd-jni-1.5.7-6.aar) реально прочитан `native_size.py`; это не собранный Unity APK.
- [источник] [Brotli](https://github.com/google/brotli), [RFC 7932](https://www.rfc-editor.org/rfc/rfc7932.html): встроенный словарь не равен custom trained dictionary; brotli Python quality11 использует стандартный формат, внешний словарь в этом API не испытывался.
- [источник] [cmix](https://github.com/byronknoll/cmix): PPM, нейромодели, высокая стоимость, рекомендация автора ≥32 GB RAM. cmix здесь не запускался; замер PPMd через pinned pyppmd — практический ориентир, не математический верхний предел качества.
- [источник] [Chimp](https://vldb.org/pvldb/vol15/p3058-liakos.pdf), [Elf](https://arxiv.org/abs/2306.16053): XOR/стирание битов с точным восстановлением. Здесь измерен простой XOR predictor, не реализации Chimp/Elf; их скорость/ratio не присваиваются нашему proxy.
- [источник] [FSST](https://github.com/cwida/fsst): статическая таблица символов, доступ по отдельной строке. [Roaring](https://roaringbitmap.org/): множества/bitmap, не упорядоченная колонка с повторами. Их полные реализации здесь не бенчмаркировались; оценки отделены.
- [источник] [HPACK RFC 7541 §7.1.3](https://www.rfc-editor.org/rfc/rfc7541.html): never-indexed для чувствительных полей; 10 байт warmed HPACK из V2 нельзя переносить на любой Authorization policy.
- [источник] [TLS 1.3 RFC 8446](https://www.rfc-editor.org/rfc/rfc8446.html), [HTTP/3 RFC 9114](https://www.rfc-editor.org/rfc/rfc9114.html): overhead, replay 0-RTT, HTTP over QUIC. В H3 модели нет TLS record overhead поверх каждого HTTP тела.
- [источник] [Android: периодические обновления](https://developer.android.com/develop/connectivity/minimize-effect-regular-updates), [оптимизация сети](https://developer.android.com/develop/connectivity/network-ops/network-access-optimization): группировка активности радио. Нельзя из уменьшения тела вычислить процент экономии батареи.

[измерено] Сами результаты — `06-experiments/results/*.json`, raw logs, полное воспроизведение V2 в `06-experiments/v2-reproduction/results/`. Каждое число в таблицах V3 получено из этих файлов либо прямо помечено [оценка].
