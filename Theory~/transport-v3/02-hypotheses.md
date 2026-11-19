# Реестр гипотез

Статус относится к точной формулировке, а не к семейству методов навсегда. «Открыта» означает, что оценка сделана, но реального измерения нужного условия нет. Общие verdict/cost/CPU/риски — `04-options-comparison.md`.

|ID|Формулировка|Статус|Доказательство / решение|
|---|---|---|---|
|A01|V2 oracle доказывает byte-exact для всех SDK values|опровергнута|audit.py: DBL_MAX, typed CTXREF;01-audit|
|A02|V2 опубликованные детерминированные числа воспроизводимы|подтверждена|reproduction_check.py:12 identical files, full run_all exit0|
|A03|V2 всегда даёт72–80% даже на иной структуре entropy|опровергнута|bench alt:43,1%|
|A04|11Б/event — Shannon lower bound генератора|опровергнута|gen.py hash dependency; extreme.py8,334Б exact roundtrip|
|H01|64К dictionary уменьшает тело на тех же пачках|подтверждена|bench V2_dict64 vs V2_dict16_l19,3профиля|
|H02|Dictionary, обученный на targetcap100, лучше прежней тренировки приcap100|подтверждена|refine.py,17,80→17,05;39,81→38,08;129,57→129,51|
|H03|Cap100 полезен, когда есть backlog|подтверждена|bench/refine, парная нарезка того же потока|
|H04|Реальные сессии позволяют cap100 без смены freshness|открыта|network.py short8контрпример; нужен реальный trace|
|H05|Универсальная линейная numeric модель улучшит matched-best >2%|опровергнута|refine.py и final_passes.py; исходная1,4%rich не additive|
|H06|Numeric history отдельно по типу улучшит matched-best >2%|опровергнута|refine.py matched targetdict, final_passes.py|
|H07|XOR64→varint улучшит эти float columns|опровергнута|bench xor и refine xor; не тест полного Gorilla/Chimp/Elf|
|H08|Настоящий Chimp/Elf улучшит реальные float columns|открыта|Только proxy; нужны данные и native benchmark|
|H09|Generic prefix delta строк улучшит body|опровергнута|bench/refine prefix|
|H10|Generic sparse edits строк выиграют value-stage у zstd|опровергнута|checkpoint.py, все3профиля хуже|
|H11|Field-specific checkpoint/state grammar окупится на реальной игре|открыта|Нет реального определения board/hash; оценка04|
|H12|Обученный Markov типа даёт доли бита в V2 generator|подтверждена|bench type_model_bits_per_event≈0,275бит|
|H13|Markov даёт столько же на независимой игре|опровергнута|bench alt≈несколько бит;04 таблица|
|H14|Trained byte-context arithmetic лучше zstd dictionary|опровергнута|models.py+bench8пачек каждого профиля|
|H15|Field/current-type/previous-type arithmetic спасает ту же модель|опровергнута|further.py,6пачек/profile, value-stage проигрывает no-dictzstd|
|H16|ANS на той же probability model исправит её проигрыш|опровергнута|[оценка] entropy model та же, backend overhead не устранит измеренный крупный разрыв|
|H17|Более сильная quantized/neural модель улучшит real holdout после code/modelcost|открыта|ROI/CPU estimate04; training/inference не запускались|
|H18|PPMd показывает простой путь к намного меньшему независимому body|опровергнута|bench batch8/wholeinstall12; V3 уже меньше wholeinstallPPMd на данных|
|H19|Rule1 hash exact reconstruction возможна в syntheticgen|подтверждена|codec.restore+test_v3+extreme.py; literal anchors, no crossbatch state|
|H20|Rule1 соответствует настоящему Mortris hash|открыта|Нет определения и корпуса; нельзя ship|
|H21|Intent replay универсален без игры/версий/RNG/residuals|опровергнута|[оценка] неизвестные inputs не восстанавливаются из intentions;03§8|
|H22|Внешний registry лучше inline shapes в полном lifecycle|открыта|V2 CAS не настоящий registry; manifestcost estimate04|
|H23|Zstd22/LDM улучшает итог >2%|опровергнута|bench/refine/final_passes; близко0%|
|H24|3 словаря по sizebucket полезнее одного16К|опровергнута|further multi3;rich хуже, gainalt0,14%|
|H25|Сильная4batch history может дать >6% на части corpus|подтверждена|further2install base−8,1%,alt−7,4% при reference8Б|
|H26|History окупится в проде после miss/retry/servermemory|открыта|further sensitivity p0/1/5/20%; state machine не реализована|
|H27|Brotli11 со встроенным dict заменит trainedzstd64|опровергнута|bench q11; alt близокdict16, но хуже64|
|H28|FSST/bitpack/EF улучшат fullframe на real data|открыта|FSST estimate; raw integer counts/fomula further, нет fullcodec|
|H29|Roaring set заменяет ordered columns без потерь|опровергнута|[оценка] set теряет порядок/повторы; ack exceptions отдельный usecase|
|H30|Delta dictionaries заметно меньше full update|подтверждена|extras.py≈29–30К против64К на выбранной смене corpus; старение версий не доказано|
|H31|Малый request-bound ack может не повторять seq диапазон|подтверждена|03§6, контрольные bytes30 01, immutable in-flight list required|
|H32|H2 warmed headers всегда10Б|опровергнута|network.py never-indexed auth67/49/49; это policy-sensitive|
|H33|Можно убрать все policy/register запросы|опровергнута|Bootstrap и idle deadline остаются; active piggyback принять|
|H34|Native zstd на устройстве стоит только16К dictionary|опровергнута|native_size.py arm64.so604К raw, AAR1,14М; фактический APK отдельно|
|H35|V3 framing cap сам по себе защищает decompress|опровергнута|MemoryError на mutated declared content-size; preflight+allocation caps обязательны|
|H36|После0-origin reset дедуп полностью безопасен без V1migration bridge|опровергнута|01-audit lost V1ack→V3key counterexample;03/08dual-key gates|
