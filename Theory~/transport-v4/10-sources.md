# Источники и происхождение доказательств

[локальный первичный] review-input/external-review.md и два извлечённых Python файла — ответ другого агента целиком, неизменённый. Его числа, помеченные расчётом, не считаются измерением; неподдержанные утверждения о выполненных итерациях опровергаются отсутствием соответствующего кода/вывода.

[локальный первичный] ../transport-v2/04-experiments/{gen,wire}.py; ../transport-v3/06-experiments/{codec,frame,bench,alternate,network,test_v3}.py и raw results. V2 свежая копия с полным прогоном находится в06-experiments/v2-rerun. results/input-sha256.json фиксирует исходныеV2/V3/Runtime/Android files до работы; verify.py проверяет неизменность.

[локальный SDK] Runtime/Internal/AnalyticsUploader.cs:SendBatch/ParseAcknowledgement; PersistenceEventSerializer.cs:AppendValue; EventValidator.cs; AnalyticsDeviceContext.cs; Native~/android/analytics/src/main/java/com/daliys/analytics/AnalyticsQueue.java. Это действующие source, не предположение по старой карте проекта.

[внешний первичный] [zstd1.5.7 C API](https://github.com/facebook/zstd/blob/v1.5.7/lib/zstd.h) — context/dictionary APIs, by-reference lifetime, frame output limits. [zstd1.5.7 frame format](https://github.com/facebook/zstd/blob/v1.5.7/doc/zstd_compression_format.md) — FHD/window/block structure. Ссылки проверены при работе; фактические версии pinned в результатах иsource SHA.

[воспроизводимый код] Полные measured JSON/log/binary fixtures в06-experiments/results. requirements.txt закрепляет версии исходного V3 окружения; Python3.14.8/macOSarm64/zstd1.5.7 — реально проверенная среда. NDK revision записан вnative-build.json. Другие платформы не проверены.

[метод] Train202/18 installs, исследовательское сравнение101/6, validation303/3, holdout909/6; новыйdrift808/4×600 с отдельным train202. Все corpus shapes и seeds заданы вworkloads.py, никакого поиска выгодных seed нет. Drift не заимствует игровую грамматикуV2; поля совместимы с логической моделью SDK, но ни один генератор не является production capture.
