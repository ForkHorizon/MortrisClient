# Независимый аудит V7 — итог

Дата проверки: 2026-10-18. Проверялись клиент `feat/v7-client` (`fe044bde937fc9801a72ccc61e23f097e7731920`) и серверный worktree `feat/v7-transport` (`0f5267df8691aa41be993f2556cfc4b0a496b906`). Основной серверный checkout не затрагивался. Исправлений, коммитов и публикаций нет; `UseTransportV7` оставлен `false`.

## Результат

| Приоритет | Вывод | Статус |
|---|---|---|
| High | Уплотнение журнала dropped ranges может пометить живую очередь как settled; следующий ack удаляет неподтверждённое событие. | Воспроизведено на Android API 35 эмуляторе |
| Medium | HTTP 307 перенаправление повторно посылает тело POST на другой origin. Конструктор клиента допускает стандартное следование редиректам. | Поведение подтверждено локальным .NET 10 harness; Unity Android handler отдельно не доказан |
| Medium | Device harness по умолчанию запускает сервер на 18081, а тестовое приложение шлёт на 18082. | Подтверждено: запуск с дефолтом не соединяется; с портом 18082 проходит |
| Low | ADR12 содержит устаревшее описание идентичности и неверное объяснение размера wire header. | Подтверждено сравнением ADR с реализацией |

### H1 — Потеря события при слиянии dropped ranges

В [`AnalyticsQueue.java`](../../Native~/android/analytics/src/main/java/com/daliys/analytics/AnalyticsQueue.java:389) при превышении лимита 1024 два самых ранних dropped диапазона объединяются в один, без проверки событий между ними. [`deleteThroughSequence`](../../Native~/android/analytics/src/main/java/com/daliys/analytics/AnalyticsQueue.java:106) затем удаляет все pending rows до `ackThrough`. Сервер трактует dropped ranges как уже settled sequence, поэтому расширенный диапазон может продвинуть ack через ещё живую строку.

**Воспроизведение.** Создать поток с 2050 событиями. Удалить выборочно нечётные sequence 1…2049, оставив чётные pending. Получается 1025 разрозненных drop ranges. При записи последнего диапазона ограничитель соединяет `[1,1]` и `[3,3]` в `[1,3]`; sequence 2 остаётся в pending до ack. Вызов `deleteThroughSequence(3)` удаляет sequence 2; следующая pending строка — 4. Scratch instrumentation probe проверил assertions до и после ack на API 35 эмуляторе (4 KB pages). См. [`dropped-range-compaction.md`](repro/dropped-range-compaction.md).

Это потеря аналитического события, если очередь получает более 1024 разрозненных dropped ranges. Само уплотнение делает такой сценарий возможным; естественная частота возникновения не измерялась. Нужна стратегия, которая не объявляет пропущенные sequence settled, пока не доказано, что там нет живых строк (например, слияние только соседних диапазонов или явное безопасное удаление строк из закрытого промежутка).

### H2 — Redirect пересылает тело POST

[`AnalyticsUploader.cs`](../../Runtime/Internal/AnalyticsUploader.cs:38) создаёт `HttpClient` со стандартным handler. [`HttpV7Transport.Send`](../../Runtime/Internal/Transport/V7Types.cs:111) помещает credential и тело в POST. На .NET 10 стандартный `HttpClientHandler` следует 307 на другой authority и пересылает POST body. В локальном двух-listener probe получатель второго origin получил синтетическое тело; Authorization не был переслан. Повторить: `dotnet run --project Theory~/transport-v7/audit/repro/RedirectBodyProbe.csproj`.

Доказательство относится к .NET 10 handler, не к Unity Android runtime. Практический охват зависит от разрешённой схемы/URL и ответа redirect от исходного сервера; remote HTTP запрещён в client options, но HTTPS URL разрешён. Для V7 POST стоит отключить auto-redirect для transport или проверять redirect и origin до повторной отправки.

### H3 — Device harness port mismatch

[`lib.sh`](../../Native~/transport-tests/e2e/lib.sh:5) выбирает `HTTP_PORT=18081`; [`V7DeviceProbe.cs`](../../Native~/transport-tests/device/V7DeviceProbe.cs:13) зашивает `10.0.2.2:18082`. Запуск с настройкой по умолчанию завершился без server requests/events. Повтор с `HTTP_PORT=18082` прошёл на API 35. Это дефект воспроизводимости harness, не транспорта в production.

### H4 — ADR12 описывает уже не тот контракт

[`12-sequence-identity-architecture.md`](../12-sequence-identity-architecture.md) описывает ключ без epoch и утверждает, что идентификатор строит сервер. Клиентская [`V7Identity.cs`](../../Runtime/Internal/Transport/V7Identity.cs:20) уже включает project, install, epoch и sequence и вычисляет derived id перед отправкой; серверная реализация согласована с этим ключом. Тезис ADR об «1–2 байтах на 100 событий» не описывает реальные поля M7 header: их стоимость зависит от varint величин и режима. Реализация не выявила несовпадения идентификаторов в проверенном диапазоне; дефект — устаревшая документация, способная ввести следующего разработчика в ошибку.

## Решение по выпуску

Не включать V7 по умолчанию, пока H1 не исправлен и не покрыт regression test. Текущий флаг остался выключенным. Остальные три замечания стоит закрыть отдельно; H2 требует проверки на целевых Unity runtimes перед оценкой фактического риска.
