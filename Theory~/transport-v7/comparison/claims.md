# Claims ledger

| Утверждение | Evidence | Условия | Статус | Допустимая публичная формулировка |
|---|---|---|---|---|
| C1 V7 raw 17,43 Б/соб. | `results/repro-native-frames.log` (1 114 241 Б / 63 943 соб.) | holdout одного дня Puzzle, C# M7 packets + V1-fallback для 200 соб., sequence identity, без HTTP/TLS/setup | REPRODUCED | «На дне Puzzle 16.10.2026 (63 943 соб.) тела V7 весили 17,4 Б/соб. при отказе от случайного event UUID; без учёта HTTP/TLS и доставки словаря» |
| C2 V7 clean 9,06 Б/соб. | то же (579 168 Б) | + условная игровая очистка, требует миграции backend/игры | REPRODUCED | «После игровой очистки — 9,1 Б/соб.; очистка применима и к V1 (102,7 Б)» |
| C3 V1 raw ≈122,57 Б/соб. | `results/repro-bench-real.log` | тела реконструированы из DB jsonb, не оригинальный HTTP | REPRODUCED | «Реконструированный V1 JSON+gzip1: 122,6 Б/соб.» |
| C4a Выигрыш V7/V1 сохраняется вне Puzzle | `results/synth-bench.json`, `public/synth-summary.csv` | синтетика, Python reference, один генератор для train/test | MEASURED (synthetic) | «На синтетическом проекте V7 весил 6–45 % от V1; при высокой энтропии выигрыш ≈2,2×» |
| C4b Подтверждение на независимом реальном проекте/дне | — | нет доступа к данным | NOT_MEASURED | не заявлять |
| C5 Cold-start окупается | report §1 | assets без сжатия ≈43 КБ, ≈413–454 соб.; доставка не реализована | MODELED | «Ориентировочно окупается за ~400–450 событий, если assets не вшиты в сборку (расчёт)» |
| C6 0 managed GC на этапе упаковки | `all_native_pack_gc_bytes: 0` в repro-native-frames; отчёты 06/09 (эмуляторы) | host .NET, типизированный ввод; Unity IL2CPP — только эмуляторы | REPRODUCED (host); MEASURED (emulator, historic) | «Этап упаковки с подготовленным вводом не аллоцирует managed-память после warmup; ввод API, native-память и доставка измеряются отдельно» |
| C7 p95 упаковки 100 соб. на телефоне | — | нет телефона | NOT_MEASURED | не заявлять; можно «на эмуляторе в среднем ≈0,14–0,20 мс (EMULATOR, стадия упаковки)» |
| C8a V7 vs GameAnalytics/Amplitude по телу запроса | `results/sdk-compare.json`, `results/sdk-runs/` (30 прогонов), report §8 | Android SDK 7.2.0 / 2.40.1 на эмуляторе, localhost HTTP, дефолты SDK, синтетический replay 600 соб., 600/600 доставлено, V7 — Python reference, без setup/TLS | MEASURED (эмулятор) | «На синтетической нагрузке (600 событий) тело V7 (warm) весило 4,3 / 71,9 Б/соб. против 43,5 / 135,9 у GameAnalytics SDK 7.2.0 и ~1100 / 1313 у Amplitude Android 2.40.1 (low/high entropy); без учёта доставки словаря, HTTP-заголовков и TLS» |
| C8b То же с учётом холодного старта | report §8 | setup ≈35 КБ (расчёт) | MODELED | «При холодном старте и одной сессии из 600 событий V7 проигрывает GameAnalytics (≈62 против 43,5 Б/соб. на low); окупается после ≈550–900 событий, если словарь не вшит в сборку» |
| C8e Puzzle (clean, обезличен.) vs SDK | report §9, `results/sdk-compare-puzzle.json` | 600 соб., эмулятор, localhost, дефолты; V7 Python reference; GA теряет булевы/пустые строки в 12 % событий | MEASURED (эмулятор) | «На обезличенном replay Puzzle (600 событий) тело V7 ≈10 Б/соб. против ≈74 у GameAnalytics SDK (с потерей булевых полей) и ≈1740 у Amplitude Android 2.40.1; без setup/TLS; при холодном старте на 600 событиях V7 (~80 Б/соб.) не лучше GameAnalytics» |
| C8f Amplitude сохраняет все поля Puzzle | report §9 | 300 событий | MEASURED | «Amplitude доставил 300/300 событий без потерь свойств» |
| C8g CPU/память SDK | `results/sdk-perf-puzzle.json`, report §10 | Android Java/ART, эмулятор, процесс целиком минус база | MEASURED (эмулятор, шумно) | «На эмуляторе GameAnalytics SDK тратил ≈0,7 мс CPU и ≈47 КБ Java-кучи на событие, Amplitude — ≈2,6 мс и ≈83 КБ (весь SDK); не сопоставимо с этапом упаковки V7 и не измерено на телефоне» |
| C8c Firebase / HyperKit | `code-size-estimates.md`, `results/code-size-estimates.json` | SDK найдены в Puzzle, runtime/upload не запускались; Firebase — предполагаемая protobuf+gzip модель, HyperKit — одно Gamestoty-событие другого состава | MODELED (не измерено) | показывать только как «ориентировочная модель, не измерение» с диапазоном и условиями; не заявлять «лучше в N раз» |
| C8d V1 хуже GameAnalytics по телу | sdk-compare.json | та же нагрузка | MEASURED (эмулятор) | «Нынешний V1 (59,9 / 162,3 Б/соб.) тяжелее GameAnalytics SDK (43,5 / 135,9) на этой синтетике» |
| C9 Sequence identity надёжна | `results/identity-harness.json` | SQLite-модель, SIGKILL; не SDK; без power-loss | MEASURED (harness) | «Исследовательский прототип очереди не теряет и не дублирует seq при падении процесса; SDK-реализация и power-loss не проверены» |
| C9b ADR 12 корректен как написан | harness | — | FAILED (5 уточнений: UUID-namespace, размер заголовка, ACK/skip, потеря хвоста, backup) | править ADR до реализации |
| C10 «0 микрофризов — гарантия» | — | — | FAILED / запрещена | не использовать |
| C11 «Лучше конкурентов» | — | — | NOT_MEASURED | не использовать |

## Короткий текст для презентации

На реальном дне Puzzle (63 943 события) тело пакета V7 весит ~17 байт на событие против ~123 байт у V1 (×7), если отказаться
от случайного UUID события; после игровой очистки — ~9 байт (очистка применима и к V1, его результат 103 Б).
Цифры — размер тела без HTTP/TLS и доставки словаря. На синтетической нагрузке в эмуляторе V7 меньше GameAnalytics SDK в 2–10 раз по телу запроса, но при холодном старте на коротких сессиях выигрыш исчезает. Firebase, HyperKit и замеры на телефоне пока не проводились.
