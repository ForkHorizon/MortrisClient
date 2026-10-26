# Как независимо проверить V4

1. Прочитать00-summary,01-audit,08-resource-budget: здесь явно отделены фактические результаты от оценок внешнего агента.
2. Открытьreview-input/external-review.md и два исходных Python файла. Запуститьexternal_audit.py: исходные self-tests пройдут, новые контрпримеры покажут дефекты.
3. ВоспроизвестиV2 из v2-rerun/run_all.sh и проверить12 deterministic outputs; логи свежего прогона уже вresults. V3 test_v3.py повторён и дал8233 события.
4. Запуститьtest_v4.py: vectors,profiles,boundaries,exact request bytes,digest,ACK binding,server retries,malformed framing,6000 mutations. Проверять не только compression/decompression, но rendered V1-minus-id bytes.
5. Сверитьpaired-matrix.json: одинаковые cap и dictionary budget, собственное обучение каждого формата. Данные сами воспроизводятся фиксированными seeds. Не суммировать stage savings.
6. Зафиксироватьselection.json до просмотраholdout-resources.json; validation303 выбралаtrailer,909/drift808 не меняют выбор. Убедиться, что drift регрессия не скрыта.
7. СопоставитьRAM с измеряемым объектом: Python CCtx, native CDict+CCtx, source bytes и whole-process RSS — разные величины. Tracemalloc не видит native allocator.
8. Native NDK результат проверить поsource SHA,compiler flags,dynamic symbols,host roundtrips. runtime_tested=false относится к Android ELF; host tests не подтверждают JNI/IL2CPP.
9. Для новой версии обязательно получить реальные queued bytes, auth/migration контракт и Android release telemetry. Без этого нельзя объявлять0 GC,≤192KiB всейRAM или<3.5ms p99.

[ограничение] Mutation fuzz без coverage не доказывает отсутствие уязвимостей. Изменённые payload могут успешно декодироваться; TLS и серверная валидация имеют свои роли. V4 не содержит сервера production и не меняет SDK.
