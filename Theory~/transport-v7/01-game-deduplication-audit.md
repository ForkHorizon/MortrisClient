# Аудит Puzzle: граница семантической очистки

Проверены текущий `PuzzleAnalyticsService.cs`, SDK uploader, Go analytics/replay,
локальная facts-модель и frontend pacing. Точные пути, SHA256 и строки сохранены
в `06-experiments/results/source-audit.json`. Серверные исходники
`puzzle_quality_integrity.go` и `puzzle_replay.go` на VPS совпали с локальными SHA.
Frontend `pacingMath.ts` на VPS отличается; `internal/facts/build_events.go` там
не найден. Поэтому facts/UI ниже описывают локальную текущую ветку, а не
утверждение о точном коде запущенного бинарника. Deployed Go-файлы тоже не
доказывают build identity бинарника, но подтверждают наличие потребителей.

В read-only транзакции PostgreSQL скопированы все события проекта
`puzzle_gravity_test`, полученные с 2026-10-16T00:00:00Z до 2026-10-17T00:00:00Z.
Источник — серверная `events`, а не synthetic generator. Label player/natural
не доказывает, что каждый источник является человеком: это утверждение producer.
Временные границы относятся к received_at; сессии могут начинаться/заканчиваться
за пределами дня. Весь день проверен, для codec benchmark взяты первые 600 событий
каждой установки, обучение/holdout разделены по SHA256 install_id.

## `placed_state_hash`

В 524934 событиях 286265 раз передан hash. Во всех 286265 случаях был CSV,
хеш точно равнялся lowercase SHA256 от его UTF-8. Несовпадений/усечений в этом
дне нет. Число и порядок ID в CSV сохраняются; серверу нельзя пересортировать
или иначе нормализовать строку до вычисления SHA.

По текущему клиенту `AddPlacedState` всегда вычисляет SHA, но CSV включает только
при UTF-8 длине<=1024. При превышении отправляется `placed_block_ids_truncated`.
В таких случаях hash нельзя восстановить по payload. Пустая строка CSV является
валидным состоянием; проверять надо наличие поля, а не `ids != ""`.

На сервере это **используемое поле**:

- `internal/analytics/puzzle_quality_integrity.go:145`: checkpoint без hash
  считается mismatch. Простое удаление испортит quality dashboard.
- `internal/analytics/puzzle_replay.go:234`: независимый hash сравнивается с CSV
  и увеличивает StateHashMismatches при расхождении.

Для группировки hash можно вычислять при ingestion (Go sha256.Sum256) либо в БД
при наличии pgcrypto. Стоимость не измерена, «доли микросекунды» не подтверждены.
Но заново вычисленный hash больше не является независимым producer checksum.
Миграция должна явно договориться, что именно требуется: идентификатор состояния
или проверка согласованности, сохранить исходные mismatches и hashes без CSV.
`game_cleanup.py` удаляет только реально выводимый, совпадающий hash и только
без truncation flag; ошибочный исходный checksum остаётся на проводе.

## `wave_attempt_id`

Все 524934 события имели это поле; несовпадений с attempt_id нет. В текущем
клиентском файле оба места записи (CommonContext и TrackDeveloper) берут `_attemptId`;
других присваиваний wave_attempt_id не найдено. Поэтому это доказанный дубль
для текущих emit paths и проверенной выборки, а не гарантия всех будущих версий.

В проверенном backend/dashboard production source употребления wave_attempt_id
как отдельного ключа не найдены. При необходимости legacy payload сервер может
восстановить alias из attempt_id до сохранения. Generic V6 уже кодировал такой
дубль ссылкой: удаление 36 текстовых символов не даёт 36 Б выигрыша в binary codec.
Дублированный app_version и house_run_id не удалялись: первый уже дешёвый,
второй отдельная lifetime сущность и не равен attempt_id.

## `interaction_id`

509790 событий дня имеют непустой interaction_id. Все имеют attempt_id и
положительный integer interaction_index. Ни одной пары (install,attempt,index)
с двумя GUID и ни одного GUID с двумя парами в этом дне не найдено.
Это сильное наблюдение, **но не доказательство crash-safe уникальности**.

DetailTaken инкрементирует `_interactionIndex`, PersistAttempt записывает
PlayerPrefs, а FlushPersistedAttempt вызывает Save с задержкой. Track/SDK queue
могут успеть сохранить событие раньше PlayerPrefs.Save. После kill процесс
восстановит старый index в прежнем attempt и повторит пару с новым GUID.
День мог просто не содержать такой гонки. Также нельзя склеивать sentinel
interaction_id=""/index0, завершения без take и legacy версии.

До замены необходимы:

1. Устойчивый монотонный counter (либо новый recovery/attempt epoch),
   сохранённый до первого durable event с новой парой.
2. Scoped key `(project_id, origin_install_id, attempt_id, interaction_index)`.
3. Версионная нормализация на ingress и перевод всех потребителей.
   Локальные facts/build_events.go, analytics quality SQL и pacingMath.ts
   используют interaction_id для корреляции, DISTINCT и orphan checks.
4. Тесты restart/recovery, background, abandoned/rejected/returned, zero/sentinel,
   старых offline payloads, коллизий и смешанных client builds.

В `game_cleanup.py` миграция включается только явным `migrate_interactions=True`.
Ряд `all_clean` — измерение при выполнении этих условий. Исходный случайный GUID
после удаления не восстанавливается; это новый semantic contract, а не
byte-for-byte сжатие исходного payload.

## Оригинальная очередь эмулятора

С разрешения пользователя запущены существующие AVD. Pixel_8 имеет игру 1.1.11,
Mortris_API_35 —1.1.14 (versionCode31, Android15/arm64). Игра при копировании
не работала. Из no_backup скопированы SQLite/WAL/SHM, без вывода metadata secrets.
В очереди 29 событий. Исходные event JSON дают 31234 Б реконструированного тела,
gzip1=3671 Б; очистка даёт 27359 Б и 3314 Б. Эта короткая пачка не заменяет holdout
из БД. Envelope/sent_at реконструированы; original queued JSON сохранён локально.

Все 29 форм первоначально не совпали по порядку ключей с jsonb-каталогом. Generic
V7 исправлен: порядок полей нормализуется по ключу, новые формы не обучаются
на holdout. Проверка перестановок — отдельный regression test. Исходные имена,
типы и значения сохраняются; порядок JSON свойств не является частью контракта.

Копии дня, SQLite и actual-value fixtures находятся в ignored results/private.
Реальные dictionary assets тоже исключены из Git: они могут содержать фрагменты
телеметрии. Авторизованный SQL/export script сохранён для воспроизводимости,
но run_all не подключается к серверу. Production UPDATE/DELETE/deploy не было.
