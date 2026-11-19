# Гипотезы и статус

|Гипотеза|Статус|Решение|
|---|---|---|
|Убрать duplicate directory/dead kind/dt0|Полный encode/decode и paired frame измерены|Простой clean вариант, малый выигрыш|
|Bitpack/EF поверх varint|Интегрированы, включая sys streams|Не выбирать по raw size без внешнего zstd|
|BOOL1bit|Реализован и fuzz проверен|Не обещать8× уменьшение после zstd|
|Decimal scaling + XOR zeros|Реализованы с exact binary guard|Не называть Chimp128/ALP paper codec|
|Локальные string indices/length split|Реализованы|Вклад в совокупном packed варианте, не additive|
|UUID/HEX raw trailer|Измерен, выиграл validation303|Кандидат V4, не все random fields вынесены|
|Hash bitmap вместо sentinel|Измерен полный conditional roundtrip|На cap500 clean лучше packed; реальное правило неизвестно|
|Zstd header synthesis|Отдельный реальный roundtrip trial|2Б savings, требует fixed negotiated window; не default|
|Малые compression tables|Измерены V3/V4 одинаковые params|Главный доступный ход для RAM с ценой по сети|
|Compressor-only native library|Две настоящие NDK сборки + host tests|Реальный размер; JNI/Android runtime gate открыт|
|MessagePack row / compressed row / chunk50|SQLite payload experiment с roundtrip|Не внедрять без миграции/partial-ACK/crash tests|
|16bit batch MAC|Опровергнута безопасность/полнота input|Immutable request rows; при внешнем binding нужен сильный полный hash|
|Range-only dedup|Не сохраняет conflict detection при overlap/rebatch|Оставить cold per-event evidence, hot range только cache|
|rANS/FSST/Chimp128/game board XDelta|Отсутствуют в коде внешнего агента, здесь не реализованы|Открыто; нет придуманного выигрыша или проигрыша|
