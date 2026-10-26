# Фактический журнал

1. Прочитаны REPORT иархив; код/сырые результаты сохранены каквход, инструкции/рекомендации из REPORT не стали задачей внедрения SDK.
2. Зафиксированы SHA-256 исходных V2/V3/V4/Runtime/Native. Врабочейкопии исправлен только common.EXP, Linux binaries неисполнялись.
3. Заново выполнены V4baseline,4 MTB5 matrices,300 fuzz-batches,2000 mutation tests,session_reset,wire и fixed_table сявным hashseed0.49 строк body идополнительные JSON воспроизведены.
4. Независимые контрпримеры подтвердили sent_delta loss,stale last alias,ignored state token,live-state mutation и trailing bytes. Разные hashseed далиразные fixed-table frames.
5. Построен V5 с fixed ushort probability array,typed stablecontext hash,integer EMA и JSON/LE prior snapshots без pickle execution. Полный asset budget измерен отдельно.
6. Новаярамка передаёт model ID,n,source length,origin и strong state ref; decoder клонирует candidate, проверяет canonical arithmetic stream,CRC/source/domain/identity и budget/deadline.
7. Исправлен initial import collision с V4 transport.py: новый модульназван frame_v5. При загрузке snapshot восстановлены derived counters/table indexes, добавлены global string-table budget и source identity checks.
8. Доглядываниянового holdoutchoices нет:FROZEN_EVALUATION задал bits14/train202/validation303/fresh1729,drift1733. Выигрыш stateless сохранился навсех 4 профилях.
9. Stateful исследован отдельно:allACK cachehit,sessionreset,SQLite lostACK/restart/conflict/cachemiss/origin denial. Добавлен 18 Б ACK,state publish после commit и no-live-state mutation при error.
10. Выполненыполная wire модель,miss sensitivity,prior mismatch,EMA asset compaction иполное Python memory accounting. Этоопровергает вывод«64KiB = веськлиент».
11. Написаннезависимый C range encoder,совпали bytes и final probabilities на 36 пачках.Полный C#/Go port и ARM-phone tests непроводились.
12. Созданы test vectors/полный 20event frame,strong post-state fixture и cross-process hashseed проверки. Завершаютсятесты,verifier ипроверкараспакованного handoff package.
