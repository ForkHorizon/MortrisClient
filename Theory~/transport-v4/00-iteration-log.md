# Журнал фактических итераций

1. Сохранён вход и извлечены два исходных code fence; зафиксированы SHA-256 V2/V3/Runtime/Android source до изменений.
2. Запущены исходные self-tests агента (pass), затем новые контрпримеры (ALP/digest/zlib/integers). Числа V4 из ответа признаны оценками, не воспроизведёнными измерениями.
3. Полностью заново выполнен оригинальный V2 run_all в отдельной копии; сравниваются12 артефактов. V3 test_v3 повторён отдельно.
4. Собраны полный core encoder и независимый bounded decoder, включая bitpacking/EF/float modes/indices/trailer/hash bitmap. Первые тесты нашли ошибку scaled-f32 reconstruction: результат обязательно заново округляется до float32 перед сериализацией. Исправлено и проверено.
5. Первый framing прогон обнаружил несоответствие ожидания единиц max_window_size у установленного Python binding; установлено защитное2MiB значение и отдельный header preflight. Слишком строгая проверка elapsed обнаружила отрицательный -1 в старом генераторе; benchmark сохраняет его как signed, defect документирован.
6. Парная матрица:3 профиля × original/100/500 × dict16/64 × V2/V3/clean/packed, плюс дополнительные варианты cap100 и replay. Каждый V4 кадр распакован и сравнен побайтово с V1-minus-id.
7. На validation303 выбран единый trailer; затем открыт holdout909 и отдельный drift808. Последний выявил регрессию, которая сохранена в отчёте, без подбора его seed или модели.
8. Измерены уровни1/3/6/9/15/19, match tables12/14/16, полная CPU pipeline/Python allocations, native CDict/CCtx/DDict. Эффект RAM не смешивается с размером словаря.
9. Измерены отдельные SQLite storage варианты, HTTP models на равной cadence; создан полный20-event fixture. Header synthesis trial реально сэкономил2байта, но оставлен отдельным опытом.
10. Собраны две compressor-only NDK arm64 библиотеки. Первый host-check упал из-за локального имени z, перекрывшего zstandard объект после ZipFile; переименовано в archive. Повтор подтвердил18 host roundtrips; Android runtime не заявлен.
11. Финальные ultra22/LDM проходы на validation ниже2%; это проверка этих двух опций, не исчерпание всех архитектур. Полноценные Chimp/rANS/FSST/XDelta остаются открытыми направлениями.
12. Добавлены полные request byte-path, exact overlay и SQLite модели durable retries/partial ACK/late response/authorization/conflict. После последних изменений запускаются весь V4 test suite и completion verifier.
