# Transport V7

**Исследование завершено 17 октября 2026 по решению пользователя.**
[Финальный отчёт](11-final-conclusions.md) — основные результаты, недостигнутые
критерии и границы реализации. Новые эксперименты в рамках V7 не планируются.

[Результат исследования](00-summary.md) — реальные данные из production DB,
прототип универсального каталога и columnar+dictionary, независимые проверки.
Исходные целевые размеры не достигнуты; ограничения и недоказанные mobile
критерии обозначены отдельно.

- [Исходный манифест](00-v7-research-charter.md)
- [Аудит Puzzle и условия миграции](01-game-deduplication-audit.md)
- [Матрица бенчмарков](02-benchmark-v7.md)
- [Формат и граница реализации](03-protocol-and-integration.md)
- [CPU/GC/Android и память](04-cpu-memory-and-device.md)
- [Воспроизведение](06-experiments/README.md)

- [Дополнительная модель целых чисел](05-integer-model-evaluation.md) — результаты эксперимента V7.

- [Unity Editor и Android IL2CPP](06-unity-runtime-validation.md) — calibrated GC и raw parity на эмуляторе.

- [Строковые таблицы и остаточная стоимость](07-string-table-evaluation.md) — размерные ablations и перенос string model в C#/Go/Unity.

- [Общий предиктор числовых колонок](08-cross-column-evaluation.md) — изолированный Python probe, без игровых правил; пока вне основного packer.

- [Полные пакеты из C#](09-full-packet-validation.md) — header/CRC и весь real holdout, отдельно от Unity column-stage evidence.

- [Независимый Go packet decoder](10-go-packet-validation.md) — catalog/aliases/auth, весь корпус и malformed/raw-body fuzz checks; без production receiver.

- [Архитектурное решение: Замена Event UUID на Sequence ID](12-sequence-identity-architecture.md) — утверждённая архитектура перехода на порядковые номера (1, 2, 3...), защита от крэшей и генерация UUID на сервере.
