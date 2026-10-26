# V4 против исправленного V5

[измерено] Полное HTTP request body: заголовок,origin,model ID,n,source length,CRC,а в stateful ещё 128bit base. Одинаковые event boundaries; own train202/18, cap100. Каждая пачка decoded и byte-exact сравнена с source, post-state encoder/decoder тоже сравнивается. Profile assets отдельные сценарии/builds, не бесплатный выбор лучшей из 4 моделей на запросе.

| Корпус | Набор/режим | Seed | Events | Batches | V4 Б/соб. | V5 stateless | Сокращение | V5 ideal stateful |
|---|---|---|---|---|---|---|---|---|
| base | historical | 101 | 8944 | 93 | 16.620975 | 13.165809 | 20.79% | 12.015429 |
| base | validation | 303 | 3121 | 32 | 16.777635 | 13.341237 | 20.48% | 12.192566 |
| base | fresh_holdout | 1729 | 6646 | 69 | 16.622630 | 13.192447 | 20.64% | 12.080800 |
| base | fresh_session_deadline30s | 1729 | 6646 | 256 | 24.179807 | 17.102919 | 29.27% | 13.361721 |
| rich | historical | 101 | 7899 | 82 | 36.966451 | 31.956450 | 13.55% | 29.933283 |
| rich | validation | 303 | 2412 | 25 | 36.885158 | 31.871061 | 13.59% | 29.973881 |
| rich | fresh_holdout | 1729 | 6652 | 69 | 37.032471 | 31.844558 | 14.01% | 29.859892 |
| rich | fresh_session_deadline30s | 1729 | 6652 | 258 | 47.811034 | 37.804871 | 20.93% | 31.160854 |
| alt | historical | 101 | 5400 | 54 | 126.604630 | 121.854815 | 3.75% | 117.540370 |
| alt | validation | 303 | 2700 | 27 | 125.455926 | 120.880000 | 3.65% | 116.461852 |
| alt | fresh_holdout | 1729 | 5400 | 54 | 127.122037 | 122.379074 | 3.73% | 118.122963 |
| alt | fresh_session_deadline30s | 1729 | 5400 | 3903 | 292.655556 | 264.302778 | 9.69% | 149.184444 |
| drift | historical | 808 | 2400 | 560 | 30.320833 | 25.892500 | 14.60% | 19.943333 |
| drift | fresh_holdout | 1733 | 2400 | 569 | 30.634583 | 26.153750 | 14.63% | 20.065000 |

[метод] Основные choices (bits14, integerEMA, stablehash, full frame) зафиксированы в FROZEN_EVALUATION.json до открытия новых 1729/1733.101 и 909 уже были известны предыдущим исследованиям, поэтому они не названы новым holdout.303 используется как validation. Синтетический train/test matching distribution не доказывает реальный production выигрыш.

[ограничение] Последняя колонка — идеальные cache hits и полный ACK. Тело stateful включает 16 Б reference, но не HTTP response; network-v5 отдельно включает 18 Б ACK. Колонка не является гарантией на реальном сервере.

[измерено] Fresh source corpus и seeds имеют counts/SHA в corpus-manifest.json. Session/deadline30s разделён от доступного backlog; числа cap100 нельзя обещать онлайн при редком трафике. Explicit Flush/background всё ещё требуют немедленной отправки.

## Граница преимущества: несовпадение приора

{
  "prior": "base train202 used on different drift product",
  "test": "fresh drift1733",
  "V5": {
    "events": 2400,
    "batches": 569,
    "bytes": 182018,
    "B_per_event": 75.84083333333334
  },
  "V4_wrong_dictionary_B_per_event": 57.67958333333333,
  "not_generalization_proof": "Cross-product mismatch, not adjacent real releases"
}

[ограничение] Это cross-product stress, не измерение соседних настоящих релизов. Неверныйприор может дать регрессию; нельзя утверждать универсальное превосходство или менять model ID без manifest/version discipline.
