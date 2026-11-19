# Synthetic Android probe: dropped-range compaction

Проверка проведена на API 35 Android emulator с 4 KB pages. Временное instrumentation-приложение использовало копию `AnalyticsQueue.java`; рабочий исходник не менялся. В очередь добавлено 2050 синтетических событий при одном открытом stream.

1. Удалить через queue API нечётные последовательности `1, 3, …, 2049`, не трогая чётные строки. При 1025 sparse ranges срабатывает лимит `MAX_DROPPED_RANGES=1024`.
2. Убедиться, что `getPending(10)` до ack содержит sequence 2.
3. Проверить dropped journal: первые две строки `[1,1]` и `[3,3]` превратились в `[1,3]`.
4. Вызвать `deleteThroughSequence(3)`.
5. Проверить, что следующий pending sequence равен 4: pending sequence 2 была удалена ack, который клиент считает settled.

Все проверки прошли. Данные только синтетические; реальные Puzzle события не использовались.
