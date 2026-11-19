# Что ещё не доказано и потенциальные проблемы

- Нет production corpus, Android CPU/battery/RSS, Unity wire capture и настоящего HTTP replay. Синтетические результаты не переводятся в обещания пользователям.
- На независимом drift V4 хуже V3 на2.34% тела. Даже наличие схемного дрейфа в генераторе не заменяет holdout по реальным релизам/установкам.
- AppVersion/BuildNumber не ограничены текущим SDK. Compact raw bound требует capability/fallback, иначе можно отвергнуть допустимую запись. Общая2MiB quota не является гарантийным максимумом памяти процесса.
- Python core/decoder и exact patcher выделяют списки/словари и сравнивают исходные bytes. Порт обязан сохранять безопасность, но его RAM/CPU/GC не измерены. SequenceMatcher с dense lexical differences может иметь плохую сложность: ограничивать работу и выбирать literal, не блокировать Flush.
- Reference decoder не реализует весь production JSON/schema/auth validator. Literal/overlay output требует самостоятельной валидации, включая n,project/origin и duplicate keys, до dedup/ACK. Это нельзя считать production-hardened parser после6000 random mutations.
- Frame transport передаёт чужое значение dict ID только после pinned manifest check; script dict objects доверенные. Нет полноценного manifest download/signature/atomic-update implementation.
- ACK модель проверяет rows/request mapping, но не настоящий asynchronous HttpClient lifecycle, process-kill междуACK иSQLite commit,JNI или policy discard path. Именно их нужно тестировать при внедрении.
- Durable model хранит identity/digest, не настоящий analytics payload. Production должен атомарно сохранять payload и dedup; отсутствие partial commit доказано лишь в SQLite-модели.
- Origin cloning/restore может создать новые divergence events в старой epoch. Новый origin protocol и авторизация ранее накопленных rows ещё не реализованы. Простой random ID и noBackup не решают все сценарии.
- Range-only dedup,16bit MAC/digest и произвольный TTL не разрешены вместо полной проверки. Hot memory можно уменьшить cold index, но disk/IOPS/retention считаются отдельно.
- История между пачками, full rANS/FSST/Chimp/ALP и board-aware delta остаются открытыми. Нет доказательства глобальной минимальности8.23Б или какой-либо Shannon floor.
- Native source pin/compile проверены, Android runtime/APK delta нет. Full compression wrapper всё ещё не JNI binding; отдельная native library может оказаться дороже существующего gzip на редком трафике.
- SQLite payload experiment не включает служебные столбцы/индексы реальной очереди, её eviction и WAL lifetime. Chunk50 требует per-event ack bitmap и безопасной миграции; коэффициент6–8× нельзя переносить без проверки.
- Число loaded CDict/DDict и concurrently decoded requests доминирует сервернуюRAM. Нужен глобальный pool/tenant quota; per-event raw ceiling не заменяет его.
- Входные V3 генераторы имеют synthetic sent_at+250 и occasional elapsed=-1; source byte oracle и physical deadline должны быть измерены заново.
