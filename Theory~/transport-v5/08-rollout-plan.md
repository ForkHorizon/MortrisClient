# До внедрения в SDK

1. Получить реальные queued V1 bytes и CLR/JSONObject outputs. Проверить в shadow-режиме числа, Unicode, порядок, реальное sent_at и exact overlay. Сохранить legacy UUID до готовности миграционного моста.
2. Перенести полный encoder/decoder в целевые языки. Проверить integer EMA, context hash, ordered maps,70bit residuals и Unicode scalar length. Текущий C-код реализует только range engine.
3. Измерить encode-only CPU/p99,GC/RSS,peak с prior/candidate/queue/network,APK delta и батарею на целевом Android. Сравнить с быстрыми и малопамятными профилямиV4. При приоритете CPU/RAM они могут оказаться лучше.
4. Проверить несколько настоящих релизов и установок на отдельном production holdout. Подготовить санитизированный train и проверить короткие literal strings в приоре, чтобы не включить пользовательские данные в SDK.
5. Начать со stateless canary:immutable modelID+SHA, bounded asset loading, auth/rate/concurrency limits, source validation и durable commit доACK. Ошибки не удаляют очередь; fallback использует исходные rows и прежнюю identity.
6. Stateful включать отдельно после проверки cache budget,miss/retry cost,typed snapshots,old-base retention,late callbacks иpartialACK. Обычный JSON не гарантирует воспроизведение compression state.
7. Игровое правило хеша использовать только после аудита реальной игры и точного shadow-сравнения. Удаление непересчитываемых полей и округление float не разрешены.

V5 оправдана как новая исследовательская версия по сетевому показателю. Автоматическая замена работающего SDK имеющимися измерениями не обоснована.
