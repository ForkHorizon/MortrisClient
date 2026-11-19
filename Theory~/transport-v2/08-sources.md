# 08. Источники

Отмечено, для какого утверждения источник используется. «Проверено» = ссылка открывалась/находилась при написании
(2026-10-16); остальное это стандартные адреса спецификаций, которые проверяющему стоит открыть самому.

## Код SDK (этот репозиторий, ветка `develop`, SDK 0.2.0)

- `Runtime/Internal/AnalyticsUploader.cs`: gzip `CompressionLevel.Fastest`, конверт пачки, ответ, 413/401/409, лимит 100.
- `Runtime/Internal/PersistenceEventSerializer.cs`: поля события и контекст устройства в каждом событии.
- `Runtime/Internal/AnalyticsDeviceContext.cs`: источник полей контекста (`Application.buildGUID` по умолчанию).
- `Runtime/Internal/EventValidator.cs`: допустимые типы значений (включая `ulong`, `decimal`).
- `Runtime/AnalyticsOptions.cs`: таймер 30 с, порог 50.
- `Native~/android/analytics/.../AnalyticsQueue.java`: `sequence`, `resetIdentity`, `getNoBackupFilesDir`, credential.

## Форматы и сжатие

- RFC 1951 DEFLATE, RFC 1952 gzip: https://www.rfc-editor.org/rfc/rfc1951 , https://www.rfc-editor.org/rfc/rfc1952
- RFC 7932 Brotli: https://www.rfc-editor.org/rfc/rfc7932
- RFC 8878 Zstandard (формат кадра, словари, magicless не входит в RFC, это расширение библиотеки):
  https://www.rfc-editor.org/rfc/rfc8878
- zstd, обучение словарей для маленьких данных: https://github.com/facebook/zstd (раздел «The case for Small Data
  compression»); python-zstandard: https://github.com/indygreg/python-zstandard ; zstd-jni:
  https://github.com/luben/zstd-jni
- RFC 9842 Compression Dictionary Transport (`dcb`/`dcz`), проверено: https://www.rfc-editor.org/rfc/rfc9842
- Protocol Buffers, wire-формат (varint, ZigZag, номера полей): https://protobuf.dev/programming-guides/encoding/
- MessagePack: https://github.com/msgpack/msgpack/blob/master/spec.md
- RFC 8949 CBOR: https://www.rfc-editor.org/rfc/rfc8949
- FlatBuffers, внутреннее устройство: https://flatbuffers.dev/internals/
- Cap'n Proto, кодирование и packing: https://capnproto.org/encoding.html
- Apache Avro, object container files: https://avro.apache.org/docs/current/specification/
- Apache Parquet, кодировки (RLE/bit-packing, delta): https://parquet.apache.org/docs/file-format/data-pages/encodings/
- Pelkonen et al., «Gorilla: A Fast, Scalable, In-Memory Time Series Database», VLDB 2015 (delta-of-delta, XOR float):
  https://www.vldb.org/pvldb/vol8/p1816-teller.pdf
- J. Duda, «Asymmetric numeral systems» (энтропийное кодирование для агрессивного варианта):
  https://arxiv.org/abs/1311.2540
- RFC 9562 UUID (порядок байт): https://www.rfc-editor.org/rfc/rfc9562
- RFC 2119 (MUST/SHOULD): https://www.rfc-editor.org/rfc/rfc2119

## Телеметрия: похожие решения

- OpenTelemetry, Resource (вынос атрибутов источника из каждой записи): https://opentelemetry.io/docs/specs/otel/resource/sdk/ ;
  OTLP: https://opentelemetry.io/docs/specs/otlp/
- Perfetto TrackEvent, интернирование строк и инкрементальное состояние на последовательность (пример stateful-
  подхода, который здесь отвергнут для сети): https://perfetto.dev/docs/instrumentation/track-events ; исходники
  интернирования (проверено): https://cobalt.googlesource.com/cobalt/+/HEAD/third_party/perfetto/include/perfetto/tracing/track_event_interned_data_index.h

## Транспорт

- RFC 9110 HTTP Semantics (`Date`, `Expect`): https://www.rfc-editor.org/rfc/rfc9110
- RFC 9113 HTTP/2, RFC 7541 HPACK: https://www.rfc-editor.org/rfc/rfc9113 , https://www.rfc-editor.org/rfc/rfc7541
- RFC 9114 HTTP/3, RFC 9204 QPACK, RFC 9000 QUIC, RFC 9001 QUIC-TLS (0-RTT, §9.2 повтор):
  https://www.rfc-editor.org/rfc/rfc9114 , https://www.rfc-editor.org/rfc/rfc9204 , https://www.rfc-editor.org/rfc/rfc9000 ,
  https://www.rfc-editor.org/rfc/rfc9001
- RFC 8446 TLS 1.3 (§5.2 запись: 5 Б заголовок + тип + тег AEAD; §8 повтор 0-RTT): https://www.rfc-editor.org/rfc/rfc8446
- `Expect: 100-continue` и задержка 350 мс в `HttpWebRequest` .NET Framework (проверено; для Mono не подтверждено):
  https://learn.microsoft.com/en-us/archive/blogs/joncole/httpwebrequest-and-expect-100-continue
- Unity и HTTP/2 у `UnityWebRequest` (проверено; про `HttpClient` под Mono данных нет):
  https://discussions.unity.com/t/support-for-http-2-with-unitywebrequest/822483

## Батарея и Android

- Android, оптимизация сетевого доступа (состояния радио, хвост активности, пакетирование), проверено:
  https://developer.android.com/training/connectivity/network-access-optimization
- Android, регулярные обновления и отложенная работа (WorkManager, аналитика как пример), проверено:
  https://developer.android.com/training/efficient-downloads/regular_updates
- `Context.getNoBackupFilesDir()`: https://developer.android.com/reference/android/content/Context#getNoBackupFilesDir()

## Приватность

- EDPB Guidelines 2/2023 on Technical Scope of Art. 5(3) of ePrivacy Directive, v2.0, принято 7 октября 2024
  (проверено): https://edpb.europa.eu/system/files/2024-10/edpb_guidelines_202302_technical_scope_art_53_eprivacydirective_v2_en_0.pdf
- GDPR, ст. 5 (минимизация, ограничение цели), ст. 25 (privacy by design): https://eur-lex.europa.eu/eli/reg/2016/679/oj
- Google Play, раздел Data safety: https://support.google.com/googleplay/android-developer/answer/10787469

## Инструменты, использованные в экспериментах

- OpenSSL 4.0.3 `s_client` (замер TLS handshake).
- Python 3.14.8; библиотеки и версии: `04-experiments/requirements.txt`.
