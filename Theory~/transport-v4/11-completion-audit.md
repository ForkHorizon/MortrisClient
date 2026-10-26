# Проверка завершения задачи

[цель] Проверить полный ответ другого агента, воспроизвести необходимые тесты, исправить выводы и подготовить исследовательскую V4. Это не задача внедрить новый transport в работающий SDK/сервер.

|Требование|Фактическое доказательство|Статус|
|---|---|---|
|Прочитать и сохранить ответ целиком|review-input/external-review.md + два неизменённых code fences|Выполнено|
|Проверить утверждения и найти ошибки|01-audit.md; external-audit.json: исходныйpass и новые counterexamples|Выполнено|
|Проверить текущую базу|Свежий V2 run_all,12 byte-identical outputs; повторV3 roundtrip8233|Выполнено|
|Попробовать лучшие варианты|Полный paired V2/V3/V4 cap/dict matrix, альтернативные integer/float/string/trailer/hash режимы|Выполнено для перечисленных моделей; глобальный оптимум не заявлен|
|Сокращать память, а не только body|Реально измеренные native/Python contexts, уровни и малые таблицы, same-paramsV3 comparator|Выполнено на host; целые Android RSS/battery не измерены|
|Проверить обещания размера библиотеки|Две pinned NDK arm64 ELF сборки и18 host roundtrips|Выполнено для build; Android runtime не сертифицирован|
|Проверить очередь и серверное состояние|SQLite payload experiments, request/row binding и durable identity/rebatch/conflict models|Выполнено как исследование; реальная миграция не внедрялась|
|Защитить точность и проверить границы|9 tests; 16100 event checks с двумярежимами, exact byte overlays,6000 mutations|Выполнено в Python reference; полная production валидация остаётся отдельной задачей|
|Независимая проверка результатов|Validation303→фиксированныйtrailer→holdout909+independentdrift808|Выполнено; выявленнаярегрессия явно сохранена|
|Учесть реальные cadence/network ограничения|Session/deadline sensitivity; H1/H2/H3 explicit models иполный20event fixture|Выполнено как модель; pcap не заявлен|
|Выпустить V4 пакет|Документы, работающий codec, fixtures/dictionaries/raw JSON/logs/commands, evidence.zip|Файлы созданы и проверены; ZIP проверяется отдельно после упаковки|
|Не испортить V2/V3/SDK|input-sha256.json + текущиеSHA, gitdiff|Неизменность проверена verifier-ом|

[граница] Открытые production gates в09-open-questions.md не выдаются за выполненные измерения. Обязательная задача этого раунда — исследование и критическая V4 — завершена при наличии проверки results/verification.json. Измерить отсутствующий трафик игры или телефон без соответствующих входов было бы выдумкой.
