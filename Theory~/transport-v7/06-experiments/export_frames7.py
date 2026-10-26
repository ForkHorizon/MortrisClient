"""Full packet evidence is explicitly separated from prior Unity column-stage proof."""
import json
from support7 import ROOT

def run():
    corpus=json.loads((ROOT/'results/native-frames-corpus.json').read_text())
    tests=json.loads((ROOT/'results/native-frames-tests.json').read_text())
    assert len(corpus)==2 and len(tests)==18
    text='''# Полные M7 пакеты из C#

`native/Frame.cs` теперь формирует настоящий M7 packet поверх общего Columns.cs:
magic/flags, catalog ID, alias epoch, SHA256-prefix dictionary ID, canonical
ULEB128 event/raw sizes, raw или standard zstd frame и CRC32. Flags0..7 покрывают
все сочетания original event UUID, numeric model и string model. Metadata16 и
cross-column experiment в этот encoder не включены.

Настоящий C# packet целиком декодируется независимым Python reference, с проверкой
project/origin, IDs/epoch/dictionary, CRC, размеров/окна zstd и всех typed values.
Это расширяет прежнюю проверку raw columns; данные не обёрнуты Python-заголовком
после native упаковки.

## Весь проверочный корпус

Тот же private day и разбиение19882 train/63943 holdout; training dictionaries
не переобучались. Raw использует logical-string catalog/dict32, conditional clean
использует прежний string-model catalog/dict32. Для каждого представления C#
сам собрал653 packets, содержащих63743 события.200 событий неизвестной схемы
оплачены full V1 gzip fallback. Это два представления одного holdout, не два
независимых игровых корпуса. Event UUID исключены по прежнему legacy identity
контракту; conditional clean требует описанной миграции игрового interaction ID.

| Вариант | C# packet bytes + fallback | Б/событие | Разница с прежним Python total, Б |
|---|---:|---:|---:|
'''
    for r in corpus:text+=f"| {r['variant']} | {r['bytes']} | {r['B_event']:.6f} | {r['byte_delta_vs_python']} |\n"
    text+='''
Все1306 packets декодированы и сравнены со всеми исходными typed values.
Для корпуса:1 warmup+1 measured pack на пачку; GC bytes каждого measured pack=0.
Суммарные количества байтов точно совпали с Python totals. Это проверка всего
holdout, а не экстраполяция четырёх native fixtures. Targets raw<13/clean<7
по-прежнему не достигнуты. HTTP/TLS/ACK/retry/setup не включены.

## Ошибки и измерение

18 protocol records ×1000 iterations: все flags0..7 с достаточным буфером и с
слишком маленьким, raw mode без dictionary,500-event compressed body больше
максимального frame до сжатия. Маленький destination возвращает false,length0;
следующий pack тем же encoder проходит. Очередь encoder не изменяет: split/V1,
повтор и ACK остаются обязанностью будущего SDK caller. Сжатие неудачно или
выгоднее raw — используется raw, если он помещается; иначе false.

Для каждого из8 native flag packets проверены2 CRC corruptions,2 чужих auth
контекста и10 CRC-valid malformed cases: flags/compression/catalog/epoch/dict,
count/raw-size, noncanonical varint,count501 и trailing compressed data.
Все отвергнуты. Это не доказательство поведения ещё не написанного Go receiver.

.NET allocation counter калибруется new byte[4096] до упаковки: результат>=4096.
Во всех18 measured intervals0 GC bytes. Persistent workspaces, CCtx/CDict,
dictionary hash и header IDs готовятся до warmup. Один encoder предназначен
для одного worker; owner обязан Dispose. Input DTO/JSON parsing и schema lookup
готовятся до таймера и не входят в проверенный этап.

| Успешный fixture | События | Среднее .NET ms | GC bytes /1000 packs |
|---|---:|---:|---:|
'''
    for r in tests:
        if r['success']:text+=f"| {r['fixture']} | {r['events']} | {r['mean_ms']:.4f} | {r['gc_bytes']} |\n"
    text+='''
## Граница готовности

Frame.cs компилируется также netstandard2.1 и выбирает имя native zstd для Unity
Android/macOS. Это **не runtime-проверка framing в Unity**: предыдущие16-fixture
Unity results покрывают Columns+zstd, не новый FrameEncoder. Полный Go frame
decoder/HTTP receiver, typed SDK ingress/catalog resolver, persistent aliases,
handshake, queue/retry/dedup/ACK и production выбор V1/V7 пока не реализованы.
Физический телефон, release CPU, FPS/thermal не измерены. SDK Runtime/, игра и
сервер не менялись; новые материалы остаются в Theory~/transport-v7/.

Воспроизведение: `run_frames.sh` после baseline/numeric/table runs. Код:
native/Frame.cs,FramesMain.cs,Frames.csproj и native_frames7.py. Evidence:
results/native-frames-tests.json,native-frames-corpus.json. Typed inputs,
manifests,catalog assets и реальные packets находятся только в private/frames.
'''
    if (ROOT/'results/go-frames.json').exists():
        text=text.replace('Полный Go frame\ndecoder/HTTP receiver, typed SDK ingress/catalog resolver, persistent aliases,',
                          'Полный Go frame decoder уже проверен отдельно в10-go-packet-validation.md.\nHTTP receiver, typed SDK ingress/catalog resolver, persistent aliases,')
    (ROOT.parent/'09-full-packet-validation.md').write_text(text)

if __name__=='__main__':run()
