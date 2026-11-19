# Для следующего независимого проверяющего

[оценка] Не доверять summary без raw-output. Особенно важно попытаться опровергнуть V3 recommended на реальном корпусе, а не ещё раз прогонять тот же генератор.

|Claim|Основание|Как опровергнуть|
|---|---|---|
|V3-C1: детерминированные числа V2 воспроизводимы|[измерено] полный run_all + reproduction-check12файлов|Новая среда с pinnedrequirements; сравнить raw artifacts|
|V3-C2: C2 V2 не общий byte-exact контракт|[измерено] audit.py DBL_MAX/typedCTXREF|Показать, что input отсекает фактический validator или что код не теряет лексему; double точно разрешён|
|V3-C3: alt даёт43,1% V2vsV1|[измерено] bench.json, seed101/202|Проверить длины/домен генератора, неизменный корпус, честные framingdict budgets|
|V3-C4: рекомендованный cap100+targetdict64 даёт17,051/38,084/129,506|[измерено] refine.json|Новый holdout по версиям, Android timings и исходные queuebytes; не признавать результат universal|
|V3-C5: without cadence gains только3,5–6,2%|[измерено] bench V3same|Проверить не изменены границы, сам rawkind1 safe subset; alternativecomp selection полнаярамка|
|V3-C6: target training полезнее сложных predictor|[измерено] matchedrefine|Обучить одинаково обе стороны, проверить dictionarytrainer seed/library/version; baseline нельзя держать на старом cap|
|V3-C7:11Б не Shannonfloor|[код]hashderived + [измерено]extreme8,334|Найти утерянные поля/хеши/metadata в fullroundtrip extreme.py; проверить first anchors/reset/неуспешный ход|
|V3-C8: rule1 точен лишь для synthetic definition|[измерено]actual decoderrestore + fullframe comparison|Заменить hash реальной игрой/undo/device randomness; проверить literal fallback|
|V3-C9: arithmetic proxy не окупился|[измерено]bench/further|Не путать value-stage с fullframe; реализовать более сильную модель и fair cost; наши отрицательные результаты не запрещают все ANS|
|V3-C10: stateful нельзя универсально отвергать|[измерено]further history4ref8|Добавить настоящий loss/crash/resync servermemory и сравнить с finalcap100targetdict, не старымV2|
|V3-C11: bounded frame исправил конкретный mutationMemoryError|[измерено]test_v3.py|Coveragefuzz, forgedcontent-size/window, concatenation, decoder library allocation beyond cap|
|V3-C12: V3test8233events и2000mutations|[измерено]v3-tests.json|Это Python only, есть149 decodable mutations; payloadparser fuzz/Unityoracle не доказаны|
|V3-C13: small request-boundack2Б достаточен при allaccepted|[оценка]spec03 immutable rowlist|Один lateack на другую rowlist либо ack до durablecommit разрушает гарантию; тестировать backend crash|
|V3-C14: epochseq требует migration/authbridge|[код]/[оценка]resetidentity + lostV1ack scenario|Прогнать partial acceptance, policyreset, clonedDB и collisioncontent; SHA256/contentlexemes policy согласовать|
|V3-C15: stoptwofinalpasses<2%|[измерено]final-passes.json|Проверить matchedtraining и честность состава методов; не глобальная оптимальность|

[оценка] Слабые места: нет настоящих событий/сервера/pcap; всего6install test,2install отдельныхfollowups; оба корпуса synthetic; build/version/drift не из реальных релизов. Compression params и модель выбраны по синтетическому validation без третьего dataset, поэтому selection optimism возможен. Targetdictionary дляbase/rich/alt разный: это не одна универсальная SDKмодель. Размер64К — runtime-onlydictionary, fullSDKnative существенно больше. Время compression benchmark шумное, часть процессов шла параллельно; сравнение cpu разных скриптов недопустимо. NativeAARизMaven не подтверждает IL2CPP/AAB/pagealignment.

[оценка] Extremecap500 — отдельная latency/CPU/игровая точка. Его декодер research, внешняя рамка hardened только поверхностно. Fullspec требования строже некоторых research helpers (например duplicatecolumns, floatfinite, fieldlimits): повторить их в целевом сервере и conformancefuzz. Для realbyteexact обязательны actualwirefixtures, kind0 до их появления безопаснее kind1. Кодекне должен удалять событие при malformedack/conflict/dictmiss.

Команды с вопросом/данными/ограничениями: `06-experiments/README.md`. Любая цифра без [измерено]/[оценка]/[код]/[источник]/[гипотеза] — повод потребовать доказательство. Оригиналы V2 не править: новые контрпримеры записывать в следующем круге.
