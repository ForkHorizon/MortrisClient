# Ограничения и потенциальные проблемы

- Нет production traffic, полного C#/Go/IL2CPP порта и измерений Android CPU/RSS/GC/APK/battery. Python reference и C entropy engine проверяют разные части работы.
- Probability table не включает prior/candidate copies, строковые таблицы, EMA, предыдущие значения и context cache. Partner statistics могут требовать O(properties²) работы; hash и state serialization тоже стоят CPU.
- Standalone source helper использует синтетический Mortris project/envelope. Настоящие auth context, middleware, model registry, SDK adapter и захват queued bytes не интегрированы.
- При V1 fallback нужны исходные rows с legacy UUID. V1-minus-id нельзя отправлять старому endpoint без моста identity. Смена transport/model не должна менять content digest.
- Fresh1729/1733 — новые seeds тех же семейств генераторов, а не настоящие соседние релизы. Чужой prior дал заметную регрессию; offline_900 дал небольшую регрессию stateless по полной сети.
- Для compression state обычный JSON может потерять исходный int/float/Decimal tag и историю overlay. Нужны typed snapshots, оригинальный transcript либо stateless reset.
- Go map iteration и C# UTF16 string.Length нельзя молча подставлять вместо определённого порядка и Python codepoint length. Полный перенос ещё должен пройти vectors.
- Registry ID1..127 конечен. Нельзя менять bytes под ID, пока старые SDK/retries ещё живы. При реальном rollout нужна политика хранения версий и namespace.
- Бюджет decoder может отвергнуть тяжёлую допустимую пачку: queue остаётся, применяется split/V4/V1 fallback. Лимиты отдельных text/overlay chunks не являются универсальными границами текущих SDK metadata.
- Source validator не заменяет весь production auth/transaction service. SQLite model проверяет нормальный reopen/rollback, а не power loss,disk full,JNI и реальные HttpClient races.
- Stateful partialACK,quarantine,credential rotation и конкуренция между commit/cache/ACK полностью не интегрированы. Cache misses могут убрать выигрыш. Per-origin snapshots способны доминировать серверную RAM; глобальные quotas обязательны.
- CRC32 не MAC; canonical re-emission и2000 mutations не являются coverage-fuzz доказательством отсутствия уязвимостей.
- Реальное правило placed_state_hash неизвестно. Оценка10.9Б/событие не является доказанным Shannon floor. Глобальная оптимальность не заявлена.
