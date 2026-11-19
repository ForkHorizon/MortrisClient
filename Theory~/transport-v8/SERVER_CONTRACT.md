# V8 transport (`/v3`)

The successor of the V7 binary transport (`docs/v7-transport.md`). It keeps V7's columns, zstd and sequence identity and changes everything around
them to cut the bytes that surround the events: a short server-issued installation id, one `Authorization` header, a frame that carries its own
context, a minimal acknowledgement, an automatic catalog and a per-project dictionary. V1 (`/v1`) and V7 (`/v2`) stay supported and unchanged; V8 is
additive (`/v3`, migration `0034_transport_v8.sql`).

Design record and measurements: MortrisClient `Theory~/transport-v8/PROTOCOL.md` (decisions D1 to D20).

All multi-byte integers inside the frame are unsigned LEB128 varints ("uvarint") unless stated; strings are `uvarint length` + UTF-8; "zigzag" is the
usual signed mapping `(n << 1) ^ (n >> 63)`.

## 1. Identity and authentication

### 1.1 Installation id

The server issues each installation a **short id**: a global counter (one sequence for all projects) written in base 62 (`0-9A-Za-z`, digits first),
without padding, so the first installations get `1`, `2`, `3`... and the id grows only when it must (`z` is followed by `10`). The id determines the
project. The internal installation key (`installations.install_id`, a UUID) is unchanged: the server maps short id to UUID, so dashboards, retention,
purge and every existing query keep working.

### 1.2 Token

```
token  = id "." key
key    = kv  tag
kv     = one base 62 character, the version of the server master key that issued the tag
tag    = 11 base64url characters (the first 8 bytes of HMAC-SHA256(masterKey[kv], "mortris-install-v1" || 0x00 || id))
```

The client sends it as `Authorization: Bearer <token>` on every `/v3` request except the first `hello`. The server recomputes the tag (constant-time
compare) and stores nothing per installation for authentication. A master key is configured as `MORTRIS_TRANSPORT_MASTER_KEYS=<kv>:<64 hex>[,<kv>:<64 hex>...]`;
the first entry issues new tokens, every entry verifies. Rotating means adding a key in front; removing a key invalidates the tokens it issued (clients get
`401 token_invalid` and say `hello` again without a token, which registers a new installation).

An installation can be revoked by adding its id to `transport_revoked` (the server answers `401 token_revoked`).

### 1.3 Failure modes

| Status | `code` | Meaning |
|---|---|---|
| 401 | `token_invalid` | missing, malformed, unknown key version or wrong tag |
| 401 | `token_revoked` | the installation was revoked |
| 429 | `rate_limited` | source IP, project or installation limit |

## 2. `POST /v3/hello`

Registers (first call) or re-synchronizes (call with a token) and tells the client everything it needs before sending packets.

Request (`application/json`, gzip allowed):

```json
{"v":3,"project_id":"puzzle","nonce":"<22 base64url chars, 16 random bytes>",
 "sdk":"mortris-unity/0.2.0","app_version":"1.1.14","build_number":"214","platform":"android",
 "epoch":0,"stream":{"base":1,"high":120,"dropped":[[1,30]]}}
```

- `nonce` is mandatory without a token. The server keeps `(project, nonce) -> installation` for the life of the installation (`transport_installs`), so a retry after a lost
  response returns **the same id, token and epoch** instead of a second installation. With a token the nonce is ignored.
- `epoch`: `0` opens a new epoch (the server allocates `max + 1`) except for a nonce retry, which returns the epoch it opened. A positive epoch
  re-synchronizes that stream (it must exist, else `404 unknown_stream`).
- `stream.base` is the first sequence the stream will ever contain; `high` the highest number the client has issued; `dropped` the ranges it discarded locally.
- `app_version`, `build_number`, `platform`, `sdk` feed the client policy match and the installation's `last_*` columns.

Response `200`:

```json
{"token":"3a.AbCdEfGhIjK0","epoch":1,"ack":0,"missing":[[1,120]],
 "shapes":18,"aliases":0,"catalog":"2ad37cc11bf52506","dict":"9f0c1d2e3a4b5c6d","p":402113}
```

`token` is returned on every call (so a client that lost it can recover it by repeating `hello` with its nonce within the retention window). `ack` is the
highest sequence with every number in `[base, ack]` received or dropped; `missing` the gaps in `[base, high]`. `shapes` and `aliases` are the counts the
server holds for this stream (see 3.3 and 3.4). `catalog` and `dict` are the asset ids (`dict` is sixteen zeros when the project has no dictionary).
`p` is the policy version (see 5).

| Status | `code` | |
|---|---|---|
| 400 | `invalid_request` | schema, unknown or disabled project, bad nonce |
| 409 | `stream_rollback` | `stream.high` is below the server's `high_water`; open a new epoch |
| 409 | `stream_conflict` | `stream.base` differs from the stream's base |
| 404 | `unknown_stream` | positive epoch that does not exist |
| 429 | `rate_limited` | registration limits (IP, project, daily cap) apply to the first call |

## 3. `POST /v3/packet`

`Content-Type: application/vnd.mortris.m8`, body at most 256 KiB, 1 to 500 events. The only header besides the standard ones is `Authorization`.

### 3.1 Frame

```
offset  size  field
0       2     magic "M8"
2       1     flags
                bit 0 (1)   body is one zstd frame (else raw)
                bit 1 (2)   integer model   (as V7 flag 2)
                bit 2 (4)   string model    (as V7 flag 4)
                bit 3 (8)   alias section present
                bit 4 (16)  shape section present
                bit 5 (32)  stream section present
                bits 6, 7   must be 0
3       8     dictionary id (first 8 bytes of SHA-256 of the dictionary; zeros = none)
11      var   epoch              uvarint, >= 1
        var   sent_at            uvarint, Unix milliseconds UTC when the client sent the packet
        var   stream_base        uvarint, >= 1
        var   high_water         uvarint, highest sequence the client has issued (>= every row's sequence)
        var   shape_count        uvarint, shapes the client's catalog holds after this packet
        var   alias_count        uvarint, alias records the client's table holds after this packet
        --    [alias section]    when bit 3 is set
        --    [shape section]    when bit 4 is set
        --    [stream section]   when bit 5 is set
        var   count              uvarint, rows (events), 1 to 500
        var   raw_size           uvarint, body size before compression, 1 to 2 MiB
        --    body               (compressed or raw, to the CRC)
last 4        CRC-32 (IEEE), little endian, over every preceding byte of the frame
```

**Alias section**: `start` (uvarint), `n` (uvarint), then `n` records, each:

```
session_id   16 bytes, canonical UUID byte order
app_version, build_number, platform, os_version, device_class, locale, sdk   strings
timezone_offset_minutes   zigzag varint (minutes, -1440..+1440 ... bounded by int32)
```

Records are appended at position `start`. `start` must not exceed the server's count (`409 aliases_missing`), records inside the known range must be identical
(`409 alias_conflict`), at most 65 536 records per stream. The origin of every record is the authenticated installation; the packet cannot name another.

**Shape section**: `start` (uvarint), `n` (uvarint), then `n` shapes, each: `event name` (string), `field_count` (uvarint, at most 64), then per field `key`
(string) and `kind` (one byte). Fields are sorted by key (byte order), keys are unique. Names and keys match `^[a-z][a-z0-9_]{0,63}$` without a trailing or
doubled underscore. Kinds: `0` int64, `1` string, `2` bool, `3` float32, `4` float64, `5` uuid, `6` hex, `10` uint64, `11` numeric text. Shapes are
appended at position `start` (position = shape id, ids only grow). A shape inside the known range must be identical (`409 shape_conflict`). A new shape
is accepted only when the project's `strict_catalog` is false (`422 shape_not_allowed` otherwise) and the project holds fewer than 4096 shapes
(`422 catalog_full`).

**Stream section**: `ranges` (uvarint), then `ranges` pairs of `from`, `to` (uvarint, `from <= to`): sequences the client discarded locally since it last told the
server. They are merged into the stream's `dropped` set.

**Body**: the V7 raw layout, unchanged: five integer columns (sequence, time, elapsed residual, shape id, alias index), then the property columns in the order of
first appearance. A row's shape id must be below `shape_count`, its alias index below `alias_count`. The server resolves `shape_count` and `alias_count`
against its own tables, so the frame needs neither a catalog id nor an alias epoch. A float32 value (kind 3) means **the shortest decimal that reads back as
that float32** (the same text a V1 JSON writer prints), converted to float64 for storage; a float64 (kind 4) is stored as is.

### 3.2 Processing

1. Authenticate (section 1), apply the IP and installation limits. A frame that does not parse is `400 invalid_packet` before any lookup.
2. Parse the header; the stream `(project, install, epoch)` must exist (`404 unknown_stream`); `stream_base` must equal the stream's base
   (`409 stream_conflict`); `high_water` below the server's means a rolled-back counter (`409 stream_rollback`).
3. Apply the alias, shape and stream sections in one transaction with the checks above.
4. The frame's `shape_count` and `alias_count` define what its rows may reference: shape ids below `shape_count`, alias indexes below `alias_count`. If they exceed what the
   server holds after the sections, `409 shapes_missing` / `409 aliases_missing`; the error body carries `details: {"shapes":N,"aliases":M,"catalog":"<id>"}` so the client resends from there.
5. Decode the body with the first `shape_count` shapes, the first `alias_count` aliases and the project's dictionary; run the events through the same validation, strict-catalog,
   clock-quality (with `sent_at`) and persistence path as a V1 batch (in chunks of 100 events, the V1 limit); derive each event id as
   `transportv7.DerivedEventID(project, internal install UUID, epoch, sequence)`.
6. In one transaction, under a per-project lock for shapes: re-check and store the shape and alias sections, store the dropped ranges and high water, settle the
   accepted, duplicate and rejected sequences, and answer. A crash before this commit only causes a harmless duplicate resend.

### 3.3 Response

```json
{"ack":120,"p":402113}
```

`ack`: every sequence in `[stream_base, ack]` is received or dropped; the client may delete up to it. Added only when non-empty:
`"rejected":[{"s":17,"n":"level_end","c":"property_too_large"}]` (final, counted as settled), `"missing":[[a,b]]`. `p` is the policy version (section 5).

### 3.4 Errors

JSON `{"code":"...","message":"..."}`:

| Status | `code` | The client |
|---|---|---|
| 400 | `invalid_packet` | drops the packet's rows into V1 and reports; never retries the same bytes |
| 404 | `unknown_stream` | sends `hello` |
| 409 | `stream_rollback` | `hello` with epoch 0 |
| 409 | `shapes_missing`, `aliases_missing` | resends the sections from the counts in the body |
| 409 | `shape_conflict` | another installation registered a different shape at that position first: fetch `GET /v3/catalog`, adopt the shape table, re-resolve its events and resend |
| 409 | `alias_conflict` | `hello` with epoch 0 (the local alias table diverged from the stream's) |
| 413 | `payload_too_large` | halves the packet size |
| 422 | `shape_not_allowed`, `catalog_full` | sends those events through V1 |
| 429, 5xx | | backs off (`Retry-After`) |

## 4. Catalog and dictionary

`GET /v3/catalog` (authenticated) returns the project's current shape table: `{"project_id","shapes":[[name,[[key,kind]...]]...]}`, positions are shape ids, gzip when the client
accepts it, `ETag` is the catalog id (the first 8 bytes of the SHA-256 of the document, the same value `hello` returns as `catalog`). Because the table is append-only, a newer
catalog is always a superset: a client that fetched it between `hello` and the next call simply has more shapes. The client adopts it as its own table, so shapes the
project already knows are never resent.

`GET /v3/assets/dictionary/{id}` (authenticated) returns an immutable dictionary (`Cache-Control: private, max-age=31536000, immutable`, gzip when accepted; `409 transport_assets_unknown` for an
unknown id).

## 5. Policy

`GET /v3/policy` returns the same `client_policy` object as V1 (`{"mode":"active","next_check_seconds":21600,"discard_pending":false}`) plus the version `p`. `p` is a 24-bit hash of
the policy document; it changes whenever the document does. `hello` and every packet response carry `p`; the client fetches the policy when `p` differs from the one it applied.
Per-project transport settings (upload interval, packet size, event sampling) are reserved for this document and are not defined yet.

## 6. Dictionary lifecycle

While a project has no dictionary the server keeps the raw (decompressed) column bodies of its packets whose frame names no dictionary (`transport_samples`, at most 400 bodies, no event ids).
Once they cover 2000 events the server builds a dictionary in the background (`transportv8.TrainDictionary`: a standard zstd dictionary of at most 16 KiB, read by the native zstd on
devices), stores it as the project's dictionary asset, deletes the samples, and from the next `hello` clients see the new `dict`. `analytics-server train-transport-dictionary --project <id>`
does the same by hand. Packets that name no dictionary (or the previous one) stay acceptable. Measured on Puzzle: 1000 events 9.12 B/event, 2000 events 8.58, 5000 events 8.35,
no dictionary 11.49; the dictionary built here, read by the C zstd, gave 8.27 on held-out packets against 8.23 for the C trainer.

## 7. Operating

1. `analytics-server migrate` (adds `0034_transport_v8.sql`).
2. Set `MORTRIS_TRANSPORT_MASTER_KEYS`; without it `/v3` answers `503 transport_unavailable`.
3. Roll the SDK out; V1 and V7 clients are unaffected. A project's `strict_catalog` decides whether clients may register new shapes.
4. Project purge removes `transport_streams`, `transport_shapes` and `transport_samples` (and with the installations, `transport_installs`).

## 8. Limits

| | |
|---|---|
| Packet | 256 KiB, 1 to 500 events |
| Shapes per project | 4096, fields per shape 64 |
| Aliases per stream | 65 536 |
| Received or dropped intervals kept per stream | 4096 (beyond that `409 stream_conflict`) |
| Nonce retention | the life of the installation |
