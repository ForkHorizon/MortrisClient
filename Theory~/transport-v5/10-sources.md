# Источники и происхождение результатов

Входные файлы пользователя:REPORT.md иtransport-v4-analysis.tgz. Отчёт, исходники и результаты сохранены вreview-input без исправлений. Его рекомендации использовались как проверяемые гипотезы.

submission-rerun содержит рабочую копию с исправленным common.EXP. Заново выполнены baseline V4,четыре MTB5 matrices,session reset,wire,fixed table сhashseed0,300 fuzz-batches и2000 mutations. Linux binaries автора не запускались; их timing на другом процессоре не считается буквально воспроизведённым.

Предыдущая база:transport-v4/{core,exact,framing,workloads},transport-v3/{alternate,network},transport-v2/{gen,wire}. Эти файлы, результаты и SDK sources не менялись;input-sha256.json иverify.py проверяют фактические bytes.

context_codec.py адаптирует предоставленную структурную модель;range_coder.py сохраняет авторский entropy reference. Новые model/frame_v5/recovery/range_native и тесты исправляют найденные дефекты. Полный C#/Go/SDK порт не заявлен.

Проверенная среда:Python3.14.8,macOS arm64; зависимости закреплены как вV4. FROZEN_EVALUATION.json задаёт выбор до нового holdout. Corpus/model manifests,raw JSON/logs иfixtures подтверждают числа; README/run_all определяют порядок воспроизведения и ограничения.
