# Полная сеть и восстановление

[модель] Одинаковые fresh base1729 events/cadence, приор/dict обучены на cap100 train202. Используется явная H1/H2/H3 модель V4 network.py: HPACK never-indexed измерен, TCP/TLS/QUIC overhead и setup0/750/4500 — допущения, не pcap. StatelessACK2 Б; экспериментальный statefulACK18 Б с next-stateID, а не бесплатные 2 Б.

| Сценарий | Пачек | V4 body / warm H2 total | V5 stateless body / total | V5 stateful body / total |
|---|---|---|---|---|
| dense_1s | 30 | 24.022 / 35.989 | 21.666 / 33.632 | 15.589 / 28.089 |
| sparse_45s | 900 | 211.039 / 570.039 | 143.841 / 502.841 | 57.460 / 432.460 |
| short_8 | 113 | 46.884 / 91.959 | 36.141 / 81.216 | 21.082 / 68.166 |
| offline_900 | 9 | 16.904 / 21.014 | 17.033 / 21.143 | 14.527 / 18.797 |

[измерено] В offline_900 V5stateless немного хуже V4 (21,143 против 21,014warmH2total). Это сохранённаярегрессияна arrival-patternstress,анедоказательствоуниверсальногоулучшения.

[вывод] При sparse traffic выигрыш тела существенно меньше влияет на полную сеть; keep-alive/deadline/piggyback требуют самостоятельного product decision. Более частые отправки не бесплатны для радио/батареи; они не измерены.

## Реальные cache misses в модели

[измерено+модель] На 2 fresh base installs,2236events, для каждого запроса реально выполняются encode/decode/SQLite dedup и ACK. При потере cache сервер возвращает MissingBase до decode, клиент повторяет stateless с теми же identities;failed body и лишний response/request учитываются. HTTP bytes — та же модель, latency не выдаётся за измеренный RTT. Поля configured и observed отличаются: например,0.01 на 23 пачках дал 0 misses.

| Настроенная p | Observed misses | Requests | Body Б/соб. с failed | Warm H2 total |
|---|---|---|---|---|
| 0 | 0 | 23 | 11.910 | 15.791 |
| 0.01 | 0 | 23 | 11.910 | 15.791 |
| 0.05 | 3 | 26 | 13.606 | 18.010 |
| 0.2 | 6 | 29 | 15.262 | 20.166 |
| 0.5 | 12 | 35 | 18.836 | 24.835 |
| 1 | 21 | 44 | 23.893 | 31.486 |

[вывод] Stateful преимущество при частых misses исчезает. Модель охватывает source/dedup correctness, но не реальные HttpClient cancellation races, server crash/power-loss scheduling, radio/battery и межпроцессную конкуренцию. Поэтому stateless — основной исследовательский кандидат.
