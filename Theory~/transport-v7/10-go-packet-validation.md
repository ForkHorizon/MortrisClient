# Независимый Go decoder полного M7

`go/frame.go` читает настоящий M7 packet, а не fixture columns. На вход API
NewFrameDecoder получает immutable server assets: catalog descriptor, alias
snapshot и dictionary. Decode получает packet bytes и отдельно authenticated
project/origin. Поля и их владельцы выводятся из catalog shape IDs внутри packet.
Ключей или типов конкретной игры в decoder нет.

В runtime Go **не получает** эталонные строки, property values, expected shape
IDs или column hints. CLI получает только assets/auth и пути packet/output.
Python сравнивает результат с исходными данными отдельно, после Go decode.

## Проверка C# → Go

Декодировано **1316 packets / 128787 events**:
1306 packets двух представлений real holdout и10 дополнительных protocol
fixtures. Это повторные представления одного корпуса, не128787 уникальных
production событий. Raw/clean содержат по63743 native events;200 остальных
событий каждого представления уже оплачены V1 fallback в размерном отчёте09.

Проверены все metadata/context/property значения, original event UUID при flag1,
uint64 max/int64 boundaries, float32/64, Unicode, exact Decimal lexemes, raw mode
без словаря и500-event compressed body. Все typed comparisons прошли. Размеры
не изменились:17.425535 Б/событие raw и9.057567 conditional-clean, без event UUID.
Трафиковые цели по-прежнему не достигнуты.

Важная деталь контроля: frozen V1 shortest-f32 formatter превращает -0 в0 и
может сокращать float32 decimal spelling. Поэтому IEEE bits сравниваются с
**исходным typed C# input** с учётом f32/f64 tag, а не с его V1 JSON rendering.
Это данные только внешнего verifier; Go decoder их не читает. Signed zero и
Decimal scale/sign сохраняются в JSON-выводе Go.

## Trust boundary

Проверяются frame length<=256KiB, CRC, magic, поддерживаемые flags0..7, catalog/
epoch/dictionary IDs, canonical varints, counts1..500, raw size<=2MiB, exact zstd
content/window/one-frame length. Skippable/trailing/oversized zstd не принимаются.
Декомпрессия выполняется только после bounded header checks. Неверные references,
sequence/order, timestamp range, alias origin, integer overflow, nonfinite
float, invalid UTF-8/strings/Decimal и property JSON>8192B отвергаются.

Каталог проверяется на enum/key/type/field/mask consistency, null containers и
semantic duplicate shapes; aliases —на type/UUID/epoch/count/duplicates.
Assets являются зарегистрированными сервером данными; схема не считается
аутентифицированной только потому, что клиент прислал её в запросе. Registry
handshake/asset distribution пока не реализованы.

Отвергнуты **112** повреждённых/auth-invalid packets: CRC-valid
неверные flags/compression/catalog/epoch/dictionary/count/size, noncanonical
varint,count501,trailing compressed data, плохой CRC и чужие project/origin.
Unit regression покрывает backward clock с elapsed=MaxInt64: порядок сложения
не должен отвергать представимый итог из-за промежуточного переполнения.
Дополнительные tests проверяют decimal bounds, signed-zero JSON, nonfinite,
malformed assets, null field types/lists и whitespace-disguised duplicates.

Fuzz target формирует корректный header/CRC вокруг произвольного **raw body**
одного события; это не fuzz всего zstd C codec или HTTP receiver.
В текущем10-second run выполнено616422 raw-body fuzz iterations без падений.

## Граница реализации

Это самостоятельный offline API decoder с error return на недопустимый packet,
не HTTP endpoint. Authentication middleware, registry persistence, ingest
transaction/dedup/ACK, retry/fallback и production server integration пока не
реализованы. Стандартный SDK Runtime/ и сервер не изменялись. При необходимости
переноса нужно использовать pinned-compatible zstd1.5.7 и адаптировать нынешние
Homebrew cgo paths; production Linux build не заявлен как проверенный.

Unity results по-прежнему покрывают Columns+zstd; новый C# framing ещё не
проверен в Unity. Физический телефон/FPS/thermal не измерены. SDK/Game semantic
cleanup остаётся отдельным слоем. Ни Go decoder, ни C# FrameEncoder не знают
названий игровых свойств или правил вычисления SHA/interaction identity.

Воспроизведение:сначала run_frames.sh (C# packets и private source assets),
затем run_go_frames.sh. Evidence:results/go-frames.json,go-frame-tests.log,
go-frame-fuzz.log. Private go-cases manifest содержит typed expected data только
для Python verifier; runtime go-frame-manifest их не содержит.
