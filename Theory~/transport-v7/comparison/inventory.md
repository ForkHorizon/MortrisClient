# Inventory: SDK, версии, устройства, недоступные условия

**Уточнение 18 октября 2026:** прежний поиск ограничился SDK workspace.
В соседнем Puzzle PackageCache найдены HyperKit 1.5.14 (`01f716126add`),
Firebase Unity 13.9.0 (`1c6830dd330f`) и Android measurement 23.0.0 в Gradle cache.
Статус «SDK недоступен/не установлен» ниже устарел; runtime replay этих двух
по-прежнему не выполнялся. [Анализ кода и модельные размеры](code-size-estimates.md)
добавлены отдельно от сохранённых измерений.

Проверено 17 октября 2026.

## Конкуренты

| SDK | Установлен/запущен? | Первичный источник (дата проверки 2026-10-17) | Что известно | Статус |
|---|---|---|---|---|
| Mortris V1 | Да (production-путь, восстановленные тела) | `Theory~/transport-v7/06-experiments` | JSON + gzip1 | MEASURED (только тела, см. report) |
| Mortris V7 | Исследовательский C# encoder, не SDK | commit `688da5d` | M7 packets | REPRODUCED |
| Firebase Analytics | **В этом workspace нет; Firebase Unity 13.9.0 найден в Puzzle PackageCache, не запускался** (нет проекта/`google-services.json`) | [Лимиты GA4/Firebase](https://support.google.com/analytics/answer/9267744) | Лимиты: событие ≤40 симв., ≤25 параметров, значение ≤100 симв., ≤500 различных имён событий на пользователя приложения. Формат и размер upload-запроса, интервал батчинга в проверенных страницах **не документированы**; TLS-захват не расшифровывает тело | DOCUMENTED_ONLY (лимиты); payload NOT_MEASURED; размер MODELED |
| GameAnalytics | **Запущен нативный Android SDK 7.2.0** (из `GA-SDK-UNITY` @ `7f661de`), фиктивные ключи, локальный адрес; аккаунта нет | [Collection API setup](https://docs.gameanalytics.com/event-tracking-and-integrations/sdks-and-collection-api/api/setup) | REST v2: `POST /v2/<game_key>/events`, тело — JSON-массив событий, gzip «настоятельно рекомендуется», `Authorization` = HMAC-SHA256 от (gzip) тела, лимит тела 1 МБ, рекомендованный flush ≈20 с, `init` на старте сессии. Обязательные default annotations на странице не перечислены | DOCUMENTED_ONLY (документация) + MEASURED на эмуляторе (payload, localhost) |
| Amplitude | **Запущен нативный Android SDK 2.40.1** (из `amplitude/unity-plugin` @ `5991461`), фиктивный ключ, локальный адрес; аккаунта нет | [HTTP V2 API](https://amplitude.com/docs/analytics/apis/http-v2-api) | `POST https://api2.amplitude.com/2/httpapi`, JSON `{api_key, events[]}`; у события обязательны `event_type` + (`user_id` или `device_id`); `insert_id` для дедупликации (окно 7 дней на `device_id`); лимит запроса <1 МБ / <2000 событий (платные планы), бесплатный — рекомендуется ≤10 событий в батче; сжатие запроса в документе **не упомянуто**. Это HTTP API, а не мобильный SDK: поведение Unity SDK (интервал flush, размеры) здесь не установлено | DOCUMENTED_ONLY (HTTP API); SDK payload NOT_MEASURED |
| Hypercell HyperKit | **В этом workspace нет; HyperKit 1.5.14 найден в Puzzle PackageCache, runtime не запускался** | Единственное найденное упоминание — вакансия Hypercell (`hypercell.global.huntflow.io/vacancy/sdk-technical-lead`): «core Unity SDK» студии. Публичного кода, пакета или документации формата не найдено | NOT_MEASURED (runtime); размер одного канала MODELED в code-size-estimates.md |

Мобильные SDK не заменялись самодельным REST-клиентом. Модельных оценок размеров
тел конкурентов в этой работе **не публикуется**: без запуска SDK они были бы выдуманными числами.

## Устройства и окружение

| Ресурс | Состояние |
|---|---|
| Физический Android ARM64 | отсутствует (`adb devices` пуст) → все phone-метрики NOT_MEASURED |
| Эмуляторы Pixel_8 (16 КБ) / Mortris_API_35 (4 КБ) | есть, но результаты — только EMULATOR; новых запусков в этой работе нет, используются сохранённые `unity-android.json` отчёта 06 |
| Unity | 6000.3.16f1/6000.4.3f1 установлены; harness для конкурентов не собирался |
| Тестовые аккаунты/проекты конкурентов | нет → внешняя доставка не проверялась |
| HTTP-приёмник Mortris (Go) | нет production receiver; есть только offline Go decoder |
| Другой день/когорта Puzzle | нет доступа и реквизитов → independent confirmation недоступен |
| Сеть / TLS capture | не выполнялось (нет SDK и устройства) |

## Запросы к пользователю (нужны для закрытия пробелов)

1. Физический Android ARM64 (желательно два уровня), USB-отладка.
2. Тестовые проекты/ключи Firebase, GameAnalytics (sandbox), Amplitude + согласованный бюджет/квоты.
3. Доступ или копия HyperKit SDK, если он существует.
4. Read-only export другого дня или когорты Puzzle (или другого проекта).
