# Firebase и HyperKit: приблизительные размеры

18 октября 2026. Статус **MODELED**, не runtime SDK benchmark.
Исправление прежнего inventory: оба SDK доступны в соседнем проекте Puzzle.

## HyperKit 1.5.14: оценка по настоящему sender

Пакет `Puzzle/Library/PackageCache/com.hypercell.hyperkit@01f716126add`.
Проверены:

- `Runtime/SDK/Gamestoty/Plugins/Android/src/Gamestoty.java`, SendEvent;
- `Runtime/SDK/Gamestoty/Gamestoty.cs`, LevelStart;
- `Runtime/Services/Analytics/Handlers/LevelStartEventHandler.cs`;
- `Runtime/Services/Analytics/Handlers/FirebaseEventBuilder.cs`.

Android Gamestoty sender формирует JSON с 18 полями: event, level, stage,
context, app_ver, device, device_id, device_idfa, device_os, два timestamp,
event_seq, event_id, sid, fps, source, campaign, test. Случайные event_id/sid
длиной 16, два timestamp длиной 19. В методе нет gzip; JSON-массив передаётся
обычному OkHttpClient. Заголовки и TLS в оценку не входят.

Два synthetic случая с пустым context:383 и551 Б на одно событие в массиве.
Оси: device10/32 символа, IDFA0/36, OS10/50, source0/20, campaign0/50;
device_id32, app version1.1.14, seq1234. В пачке скобки амортизируются;
округлённый ориентир **380–550 Б**. Это выбранные сценарии, не нижняя/верхняя
граница всех событий. Дополнительный context, длинные имена и fps увеличат размер.
Данные synthetic, код отправки не запускался и наружу ничего не отправлялось.

LevelStartEventHandler также отправляет события через Firebase, а для первого
уровня возможны дополнительные Firebase/Adjust вызовы. HyperKit нельзя считать
одним JSON-протоколом. Gamestoty level_start не несёт все свойства Puzzle replay:
делить383–551 на9,96 и объявлять эквивалентный выигрыш некорректно.

## Firebase: сценарная proxy-модель

Найдены Firebase Unity 13.9.0 и dependency Android firebase-analytics 23.0.0.
Публичный Android Firebase repository не содержит Analytics implementation:
[официальный репозиторий](https://github.com/firebase/firebase-android-sdk).
Локальные Unity wrappers/бинарники сами по себе не дают проверенной upload-схемы.
Поэтому этот расчёт **не является размером output настоящего Firebase encoder**.

Чтобы всё же дать ориентир, на тех же600 private replay events посчитана простая
сценарная модель: protobuf length-delimited event name, timestamp varint,
repeated key/value messages; строки UTF-8, int64 varint, float64 fixed64,
bool как строки. Конкретные field tags/layout выбраны для модели и не извлечены
из Google SDK. Сверху gzip level1 и предполагаемые128/512/2048 случайных байт
metadata на пачку. Реальная metadata может иметь другой размер и сжимаемость;
реальные batching и gzip policy этой версии не подтверждены.

| Условие | Предполагаемое сжатое тело, Б/событие |
|---|---:|
|100 событий/пачку, исходные пользовательские поля|45,70–66,54|
|10 событий/пачку, исходные пользовательские поля|116,51–317,66|
|100/пачку, первые25 полей и строки до100 символов|44,63–65,45|
|10/пачку, первые25 полей и строки до100 символов|114,95–315,92|

Отсюда ориентир **≈45–320 Б** для выбранных сценариев, не доверительный интервал
и не гарантированный диапазон Firebase. Без предполагаемого gzip модель даёт
около554–770 Б/событие. Нельзя обещать100–150 Б, не оговаривая размер пачки и
сжатие. Усечение первых25 полей — лишь сценарий чувствительности, не имитация
реального правила выбора параметров Firebase.

Дополнительно подтверждено по HyperKit FirebaseEventBuilder: строка длиннее100
обрезается, bool переводится в lower-case string, добавляются game/session/level
поля. Это конкретное поведение HyperKit wrapper, не доказательство wire-size
нативного Firebase SDK. Для реального сравнения нужны runtime upload bytes.

## Воспроизведение

`scripts/estimate_unmeasured.py` читает существующий private replay, не меняет
SDK/игру и не открывает сеть. Запуск из SDK root:

```sh
PYTHONDONTWRITEBYTECODE=1 'Theory~/transport-v3/06-experiments/.venv/bin/python' 'Theory~/transport-v7/comparison/scripts/estimate_unmeasured.py'
```

Результат: [aggregate JSON](results/code-size-estimates.json), без значений
private events; SHA replay и двух проверенных source files фиксируют вход.
Self-checks проверяют canonical varint/framing и roundtrip gzip каждого тела.
Реальные протоколы/доставка/CPU/GC Firebase и всего HyperKit не измерялись.
