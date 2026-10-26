"""Wire encoders for transport-V2 experiments (evidence only, NOT product code).

v1_json          exact replica of SDK 0.2.0 batch body (AnalyticsUploader.SendBatch + AnalyticsQueue payload_json)
json_variant     V1 JSON with individual optimizations toggled (ablation on the JSON baseline)
msgpack_rows / cbor_rows   V1 structure, binary format swap only
msgpack_compact  row-wise MessagePack with numeric ids, context table, deltas, binary uuid/hash
pb_generic       Protobuf wire format, SDK-generic Prop{key,value} messages (no per-game codegen)
pb_typed         Protobuf wire format with per-game generated field numbers (codegen)
mtb2_encode      the proposed columnar MTB2 payload (01-protocol-spec.md section 5); mtb2_decode is its inverse

Protobuf schema that pb_generic / pb_typed hand-encode (wire-compatible with protoc output for this .proto):
  message Batch   { uint32 version = 1; bytes install_id = 2; uint64 first_seq = 3; uint64 base_time = 4;
                    repeated Context ctx = 5; repeated Event ev = 6; }
  message Context { bytes session_id = 1; string app_version = 2; string build_number = 3; string platform = 4;
                    string os_version = 5; string device_class = 6; string locale = 7; sint32 tz_minutes = 8; }
  message Event   { uint32 type = 1; sint64 dt_ms = 2; uint32 ctx = 3; sint64 elapsed_residual = 4;
                    repeated Prop props = 5; }                       // pb_generic
  message Prop    { uint32 key = 1; oneof v { sint64 i = 2; string s = 3; bytes b = 4; float f = 5; bool bo = 6; } }
  pb_typed: Event fields 1-4 as above, then each property key k is field (4 + registry_id(k)) typed by value
  (sint64 / string / bytes / float), i.e. what per-game codegen would emit. UUIDs -> bytes(16), hex -> bytes.
"""
import json
import re
import struct
import uuid as uuidlib
from decimal import Decimal

import cbor2
import msgpack

from gen import PROJECT_ID, iso_ms

DEVICE_KEYS = ("app_version", "build_number", "platform", "os_version", "device_class", "locale",
               "timezone_offset_minutes")
GAME_CTX_KEYS = ("app_version", "attempt_id", "wave_attempt_id", "city_id", "house_id", "attempt_number", "wave_index")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
HEX_RE = re.compile(r"^(?:[0-9a-f]{2}){8,}$")


# ---------------------------------------------------------------- helpers
def f32_repr(x):
    """Shortest decimal that round-trips through float32, like C# float.ToString("R")."""
    for p in range(1, 10):
        s = f"{x:.{p}g}"
        if struct.unpack("<f", struct.pack("<f", float(s)))[0] == x:
            return s
    return repr(x)


def jdump(o):
    """Compact JSON like Android org.json: no spaces, '/' escaped as '\\/', float32 shortest repr."""
    if isinstance(o, dict):
        return "{" + ",".join(json.dumps(k) + ":" + jdump(v) for k, v in o.items()) + "}"
    if isinstance(o, list):
        return "[" + ",".join(jdump(v) for v in o) + "]"
    if isinstance(o, bool) or o is None:
        return json.dumps(o)
    if isinstance(o, float):
        return f32_repr(o) if _is_f32(o) else repr(o)
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, str):
        return json.dumps(o, ensure_ascii=False).replace("/", "\\/")
    return str(o)


def _is_f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0] == x


def uvarint(n):
    assert n >= 0
    out = bytearray()
    while n >= 0x80:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def zz(n):
    return (n << 1) ^ (n >> 63)


def unzz(n):
    return (n >> 1) ^ -(n & 1)


def read_uvarint(buf, pos):
    shift = res = 0
    while True:
        b = buf[pos]
        pos += 1
        res |= (b & 0x7F) << shift
        if not b & 0x80:
            return res, pos
        shift += 7
        if shift > 63:
            raise ValueError("varint overflow")


def sent_at(batch):
    return batch[-1]["ts"] + 250


# ---------------------------------------------------------------- V1 exact
def v1_event(e):
    d = {"event_id": e.get("event_id"), "session_id": e["session_id"], "name": e["name"],
         "occurred_at_client": iso_ms(e["ts"]), "session_elapsed_ms": e["session_elapsed_ms"]}
    for k in DEVICE_KEYS:
        d[k] = e[k]
    d["properties"] = e["properties"]
    d["sequence"] = e["sequence"]
    return d


def v1_json(inst, batch, without_event_id=False):
    """without_event_id=True gives the V1 body minus event_id fields: the equivalence target for V2 decoding."""
    evs = [v1_event(e) for e in batch]
    if without_event_id:
        for d in evs:
            del d["event_id"]
    events = "[" + ",".join(jdump(d) for d in evs) + "]"
    return ('{"schema_version":1,"project_id":' + json.dumps(PROJECT_ID) + ',"install_id":' +
            json.dumps(inst.install_id) + ',"sdk":{"name":"mortris-unity","version":"0.2.0"},"sent_at_client":' +
            json.dumps(iso_ms(sent_at(batch))) + ',"events":' + events + "}").encode()


def v1_response(batch, server_time_ms):
    """Current server response (shape from AnalyticsUploader.BatchResponse). Assumed all accepted."""
    return jdump({"accepted": [e["event_id"] for e in batch], "duplicates": [], "rejected": [],
                  "server_time": iso_ms(server_time_ms),
                  "client_policy": {"mode": "Active", "next_check_seconds": 3600, "discard_pending": False}}).encode()


# ---------------------------------------------------------------- JSON ablation
class Registry:
    """Numeric ids for names/keys. Stands in for a build-time generated schema table."""

    def __init__(self):
        self.ids = {}

    def id(self, s):
        return self.ids.setdefault(s, len(self.ids) + 1)


REG = Registry()


def json_variant(inst, batch, dedupe=False, drop_event_id=False, hoist_device=False, hoist_session=False,
                 time_delta=False, short_keys=False, hoist_game=False):
    ctxs, ctx_idx, gctxs, gctx_idx = [], {}, [], {}
    evs, prev_ts, prev_el = [], batch[0]["ts"], {}
    for e in batch:
        p = dict(e["properties"])
        if dedupe:
            if p.get("wave_attempt_id") is not None and p.get("wave_attempt_id") == p.get("attempt_id"):
                del p["wave_attempt_id"]
            if p.get("app_version") == e["app_version"]:
                del p["app_version"]
        d = {}
        if not drop_event_id:
            d["event_id"] = e["event_id"]
        ctx = {}
        (ctx if hoist_session else d)["session_id"] = e["session_id"]
        d["name"] = REG.id(e["name"]) if short_keys else e["name"]
        if time_delta:
            d["dt"] = e["ts"] - prev_ts
            prev_ts = e["ts"]
            key = e["session_id"]
            pe = prev_el.get(key)
            d["el"] = e["session_elapsed_ms"] if pe is None else e["session_elapsed_ms"] - (pe[0] + e["ts"] - pe[1])
            prev_el[key] = (e["session_elapsed_ms"], e["ts"])
        else:
            d["occurred_at_client"] = iso_ms(e["ts"])
            d["session_elapsed_ms"] = e["session_elapsed_ms"]
        for k in DEVICE_KEYS:
            (ctx if hoist_device else d)[k] = e[k]
        if ctx:
            fp = jdump(ctx)
            if fp not in ctx_idx:
                ctx_idx[fp] = len(ctxs)
                ctxs.append(ctx)
            d["c"] = ctx_idx[fp]
        if hoist_game:
            g = {k: p.pop(k) for k in GAME_CTX_KEYS if k in p}
            if g:
                fp = jdump(g)
                if fp not in gctx_idx:
                    gctx_idx[fp] = len(gctxs)
                    gctxs.append(g)
                d["g"] = gctx_idx[fp]
        d["properties"] = {str(REG.id(k)): v for k, v in p.items()} if short_keys else p
        d["sequence"] = e["sequence"]
        evs.append(d)
    if short_keys:
        evs = [{str(REG.id(k)): v for k, v in d.items()} for d in evs]
    body = {"schema_version": 2 if short_keys else 1, "project_id": PROJECT_ID, "install_id": inst.install_id,
            "sdk": {"name": "mortris-unity", "version": "0.2.0"}, "sent_at_client": iso_ms(sent_at(batch))}
    if time_delta:
        body["base_time"] = batch[0]["ts"]
    if ctxs:
        body["contexts"] = ctxs
    if gctxs:
        body["game_contexts"] = gctxs
    body["events"] = evs
    return jdump(body).encode()


# ---------------------------------------------------------------- binary format swaps (no restructuring)
def _v1_obj(inst, batch):
    return {"schema_version": 1, "project_id": PROJECT_ID, "install_id": inst.install_id,
            "sdk": {"name": "mortris-unity", "version": "0.2.0"}, "sent_at_client": iso_ms(sent_at(batch)),
            "events": [v1_event(e) for e in batch]}


def msgpack_rows(inst, batch):
    return msgpack.packb(_v1_obj(inst, batch), use_single_float=True)


def cbor_rows(inst, batch):
    return cbor2.dumps(_v1_obj(inst, batch))


# ---------------------------------------------------------------- compact row-wise (MessagePack / Protobuf)
def _bin_value(v):
    if isinstance(v, str) and UUID_RE.match(v):
        return uuidlib.UUID(v).bytes
    if isinstance(v, str) and HEX_RE.match(v):
        return bytes.fromhex(v)
    return v


def _compact_rows(batch):
    """Shared restructuring: ctx table (session+device), dt, elapsed residual, dedupe, numeric ids, binary ids."""
    ctxs, idx, rows, prev_ts, prev_el = [], {}, [], batch[0]["ts"], {}
    for e in batch:
        c = (e["session_id"],) + tuple(e[k] for k in DEVICE_KEYS)
        if c not in idx:
            idx[c] = len(ctxs)
            ctxs.append(c)
        pe = prev_el.get(c[0])
        el = e["session_elapsed_ms"] if pe is None else e["session_elapsed_ms"] - (pe[0] + e["ts"] - pe[1])
        prev_el[c[0]] = (e["session_elapsed_ms"], e["ts"])
        p = dict(e["properties"])
        if p.get("wave_attempt_id") is not None and p.get("wave_attempt_id") == p.get("attempt_id"):
            del p["wave_attempt_id"]
        if p.get("app_version") == e["app_version"]:
            del p["app_version"]
        rows.append((REG.id(e["name"]), e["ts"] - prev_ts, idx[c], el, {REG.id(k): _bin_value(v) for k, v in p.items()}))
        prev_ts = e["ts"]
    return ctxs, rows


def msgpack_compact(inst, batch):
    ctxs, rows = _compact_rows(batch)
    ctxs = [[uuidlib.UUID(c[0]).bytes, *c[1:]] for c in ctxs]
    return msgpack.packb([2, uuidlib.UUID(inst.install_id).bytes, batch[0]["sequence"], batch[0]["ts"], ctxs,
                          [list(r) for r in rows]], use_single_float=True)


def _pb_key(field, wt):
    return uvarint(field << 3 | wt)


def _pb_ld(field, b):
    return _pb_key(field, 2) + uvarint(len(b)) + b


def _pb_value(v):
    """oneof value: 2 sint64, 3 string, 4 bytes, 5 fixed32 float, 6 bool."""
    if isinstance(v, bool):
        return _pb_key(6, 0) + uvarint(int(v))
    if isinstance(v, int):
        return _pb_key(2, 0) + uvarint(zz(v))
    if isinstance(v, float):
        return _pb_key(5, 5) + struct.pack("<f", v)
    if isinstance(v, bytes):
        return _pb_ld(4, v)
    return _pb_ld(3, v.encode())


def _pb_header(inst, batch, ctxs):
    out = _pb_key(1, 0) + uvarint(2) + _pb_ld(2, uuidlib.UUID(inst.install_id).bytes)
    out += _pb_key(3, 0) + uvarint(batch[0]["sequence"]) + _pb_key(4, 0) + uvarint(batch[0]["ts"])
    for c in ctxs:
        cb = _pb_ld(1, uuidlib.UUID(c[0]).bytes)
        for i, v in enumerate(c[1:-1]):
            cb += _pb_ld(2 + i, v.encode())
        cb += _pb_key(8, 0) + uvarint(zz(c[-1]))
        out += _pb_ld(5, cb)
    return out


def pb_generic(inst, batch):
    ctxs, rows = _compact_rows(batch)
    out = _pb_header(inst, batch, ctxs)
    for t, dt, c, el, props in rows:
        eb = _pb_key(1, 0) + uvarint(t) + _pb_key(2, 0) + uvarint(zz(dt))
        if c:
            eb += _pb_key(3, 0) + uvarint(c)
        if el:
            eb += _pb_key(4, 0) + uvarint(zz(el))
        for k, v in props.items():
            eb += _pb_ld(5, _pb_key(1, 0) + uvarint(k) + _pb_value(v))
        out += _pb_ld(6, eb)
    return out


def pb_typed(inst, batch):
    """Per-game codegen: each property key is a direct field (number 5 + registry id), wire type by value type."""
    ctxs, rows = _compact_rows(batch)
    out = _pb_header(inst, batch, ctxs)
    for t, dt, c, el, props in rows:
        eb = _pb_key(1, 0) + uvarint(t) + _pb_key(2, 0) + uvarint(zz(dt))
        if c:
            eb += _pb_key(3, 0) + uvarint(c)
        if el:
            eb += _pb_key(4, 0) + uvarint(zz(el))
        for k, v in props.items():
            f = 4 + k
            if isinstance(v, bool) or isinstance(v, int):
                eb += _pb_key(f, 0) + uvarint(zz(int(v)))
            elif isinstance(v, float):
                eb += _pb_key(f, 5) + struct.pack("<f", v)
            else:
                eb += _pb_ld(f, v if isinstance(v, bytes) else v.encode())
        out += _pb_ld(6, eb)
    return out


# ---------------------------------------------------------------- MTB2 columnar (proposed)
# value type tags (shape table). See 01-protocol-spec.md section 5.4
T_INT, T_STR, T_BOOL, T_F32, T_F64, T_UUID, T_HEX, T_NULL, T_ALIAS, T_CTXREF, T_U64, T_NUMTEXT = range(12)
SDK_NAME, SDK_VERSION = "mortris-unity", "0.2.0"
CTX_FIELDS = DEVICE_KEYS  # ctx table field order after session uuid


def _vtype(v):
    if v is None:
        return T_NULL
    if isinstance(v, bool):
        return T_BOOL
    if isinstance(v, int):
        return T_INT if v < 2 ** 63 else T_U64
    if isinstance(v, float):
        return T_F32 if _is_f32(v) else T_F64  # a real SDK tags float vs double from the CLR type
    if isinstance(v, Decimal):
        return T_NUMTEXT
    if UUID_RE.match(v):
        return T_UUID
    if HEX_RE.match(v):
        return T_HEX
    return T_STR


class _Tab:
    def __init__(self):
        self.items, self.idx = [], {}

    def id(self, v):
        if v not in self.idx:
            self.idx[v] = len(self.items)
            self.items.append(v)
        return self.idx[v]


def mtb2_encode(inst, batch, columnar=True, aliases=True, int_delta=True, with_install=True, known=None,
                sections=None):
    """Returns payload bytes (before compression).
    columnar=False writes the identical tokens row-major (isolates layout effect; not decodable here).
    known: set of 8-byte fingerprints the server already holds (content-addressed ctx/shape cache, spec 5.6).
    sections: optional dict to receive per-section byte counts."""
    strs, uuids, hexes = _Tab(), _Tab(), _Tab()
    ctx_tab, shape_tab = _Tab(), _Tab()
    # ---- pass 1: shapes and contexts
    ev_shape, ev_ctx = [], []
    for e in batch:
        c = (e["session_id"],) + tuple(e[k] for k in CTX_FIELDS)
        ev_ctx.append(ctx_tab.id(c))
        ctxd = dict(zip(CTX_FIELDS, c[1:]))
        fields = []
        keys = list(e["properties"])
        for k, v in e["properties"].items():
            t = _vtype(v)
            if aliases and k in ctxd and ctxd[k] == v:
                t = T_CTXREF
            fields.append((k, t))
        ev_shape.append((e["name"], tuple(fields), keys))
    # alias detection: per (name, fields) keep T_ALIAS(j) only if it holds for every event of that shape in batch
    shape_alias = {}
    if aliases:
        for (name, fields, keys), e in zip(ev_shape, batch):
            sk = (name, fields)
            p = e["properties"]
            cand = {i: {j for j in range(i) if fields[j][1] == fields[i][1] and p[keys[j]] == p[keys[i]]}
                    for i in range(len(fields)) if fields[i][1] in (T_UUID, T_STR, T_HEX, T_INT)}
            if sk not in shape_alias:
                shape_alias[sk] = cand
            else:
                shape_alias[sk] = {i: shape_alias[sk][i] & cand.get(i, set()) for i in shape_alias[sk]}
    ev_shape_id = []
    for name, fields, _ in ev_shape:
        al = shape_alias.get((name, fields), {})
        f2 = tuple((k, (T_ALIAS, min(al[i])) if al.get(i) else t) for i, (k, t) in enumerate(fields))
        ev_shape_id.append(shape_tab.id((name, f2)))
    # ---- columns
    cols, col_order = {}, []

    def col(key):
        if key not in cols:
            cols[key] = []
            col_order.append(key)
        return cols[key]

    shape_col, ctx_col, dt_col, el_col = [], [], [], []
    prev_ts, prev_el = batch[0]["ts"], {}
    for e, sid, cid in zip(batch, ev_shape_id, ev_ctx):
        shape_col.append(sid)
        ctx_col.append(cid)
        dt_col.append(e["ts"] - prev_ts)
        prev_ts = e["ts"]
        pe = prev_el.get(cid)
        el_col.append(e["session_elapsed_ms"] if pe is None else e["session_elapsed_ms"] - (pe[0] + e["ts"] - pe[1]))
        prev_el[cid] = (e["session_elapsed_ms"], e["ts"])
        name, fields = shape_tab.items[sid]
        for (k, t), v in zip(fields, e["properties"].values()):
            if isinstance(t, tuple) or t in (T_CTXREF, T_NULL):
                continue
            col((k, t)).append(v)

    def rle(vals):
        out, i = bytearray(), 0
        while i < len(vals):
            j = i
            while j < len(vals) and vals[j] == vals[i]:
                j += 1
            out += uvarint(vals[i]) + uvarint(j - i)
            i = j
        return bytes(out)

    def enc_col(t, vals):
        """Returns list of per-value byte tokens plus a column prefix."""
        if t == T_INT:
            raw = [uvarint(zz(v)) for v in vals]
            if int_delta:
                dl, p = [], 0
                for v in vals:
                    dl.append(uvarint(zz(v - p)))
                    p = v
                if sum(map(len, dl)) < sum(map(len, raw)):
                    return b"\x01", dl
            return b"\x00", raw
        if t == T_STR:
            return b"", [uvarint(strs.id(v)) for v in vals]
        if t == T_NUMTEXT:
            return b"", [uvarint(strs.id(str(v))) for v in vals]
        if t == T_U64:
            return b"", [uvarint(v) for v in vals]
        if t == T_UUID:
            return b"", [uvarint(uuids.id(v)) for v in vals]
        if t == T_HEX:
            return b"", [uvarint(hexes.id(v)) for v in vals]
        if t == T_BOOL:
            return b"", [bytes([v]) for v in vals]
        if t == T_F32:
            return b"", [struct.pack("<f", v) for v in vals]
        if t == T_F64:
            return b"", [struct.pack("<d", v) for v in vals]
        raise ValueError(t)

    enc = [(k, t, *enc_col(t, cols[(k, t)])) for (k, t) in col_order]
    # ---- serialize tables (strings referenced by index into strs)
    known = known if known is not None else set()
    fps = set()
    ctx_bytes = bytearray(uvarint(len(ctx_tab.items)))
    for c in ctx_tab.items:
        body = uuidlib.UUID(c[0]).bytes + b"".join(uvarint(strs.id(v)) for v in c[1:-1]) + uvarint(zz(c[-1]))
        fp = _fp(b"C" + uuidlib.UUID(c[0]).bytes + jdump(list(c[1:])).encode())
        fps.add(fp)
        if fp in known:
            ctx_bytes += b"\x01" + fp
        else:
            ctx_bytes += b"\x00" + body
    shape_bytes = bytearray(uvarint(len(shape_tab.items)))
    for name, fields in shape_tab.items:
        fp = _shape_fp(name, fields)
        fps.add(fp)
        if fp in known:
            shape_bytes += b"\x01" + fp
            continue
        sb = uvarint(strs.id(name)) + uvarint(len(fields))
        for k, t in fields:
            sb += uvarint(strs.id(k))
            sb += bytes([T_ALIAS]) + uvarint(t[1]) if isinstance(t, tuple) else bytes([t])
        shape_bytes += b"\x00" + sb
    # column directory: (key str idx, type, mode)
    coldir = bytearray(uvarint(len(enc)))
    for k, t, prefix, _ in enc:
        coldir += uvarint(strs.id(k)) + bytes([t]) + prefix
    head = bytes([2]) + uvarint(1 if with_install else 0) + (uuidlib.UUID(inst.install_id).bytes if with_install else b"")
    seqs = [e["sequence"] for e in batch]
    gaps = [(i, seqs[i] - seqs[i - 1] - 1) for i in range(1, len(seqs)) if seqs[i] != seqs[i - 1] + 1]
    head += uvarint(seqs[0]) + uvarint(len(batch)) + uvarint(len(gaps)) + b"".join(uvarint(i) + uvarint(g) for i, g in gaps)
    head += uvarint(batch[0]["ts"]) + uvarint(zz(sent_at(batch) - batch[-1]["ts"]))
    meta = uvarint(strs.id(PROJECT_ID)) + uvarint(strs.id(SDK_NAME)) + uvarint(strs.id(SDK_VERSION))
    tables = uvarint(len(strs.items)) + b"".join(uvarint(len(s.encode())) + s.encode() for s in strs.items)
    tables += uvarint(len(uuids.items)) + b"".join(uuidlib.UUID(u).bytes for u in uuids.items)
    tables += uvarint(len(hexes.items)) + b"".join(uvarint(len(h) // 2) + bytes.fromhex(h) for h in hexes.items)
    sys_cols = [[uvarint(s) for s in shape_col], None, [uvarint(zz(d)) for d in dt_col], [uvarint(zz(x)) for x in el_col]]
    ctx_rle = rle(ctx_col)
    if columnar:
        body = b"".join(sys_cols[0]) + ctx_rle + b"".join(sys_cols[2]) + b"".join(sys_cols[3])
        body += b"".join(b"".join(toks) for _, _, _, toks in enc)
    else:
        # row-major: same tokens interleaved per event (ctx stays RLE; it is tiny)
        it = {i: iter(toks) for i, (_, _, _, toks) in enumerate(enc)}
        key_pos = {(k, t): i for i, (k, t, _, _) in enumerate(enc)}
        body = bytearray(ctx_rle)
        for n, sid in enumerate(shape_col):
            body += sys_cols[0][n] + sys_cols[2][n] + sys_cols[3][n]
            for k, t in shape_tab.items[sid][1]:
                if not isinstance(t, tuple) and t not in (T_CTXREF, T_NULL):
                    body += next(it[key_pos[(k, t)]])
        body = bytes(body)
    tables += meta
    out = head + tables + bytes(ctx_bytes) + bytes(shape_bytes) + bytes(coldir) + body
    if sections is not None:
        sections.update(header=len(head), tables=len(tables), contexts=len(ctx_bytes), shapes=len(shape_bytes),
                        coldir=len(coldir), body=len(body), fps=fps)
    return out


def _fp(b):
    import hashlib
    return hashlib.blake2b(b, digest_size=8).digest()


def _shape_fp(name, fields):
    return _fp(b"S" + jdump([name, [[k, list(t) if isinstance(t, tuple) else t] for k, t in fields]]).encode())


def mtb2_decode(buf, ctx_cache=None, shape_cache=None):
    """Inverse of mtb2_encode(columnar=True, with_install=True). Returns (install_id, events) in V1-equivalent form
    (no event_id: identity is (install_id, sequence)). Bounds-checked: raises ValueError on malformed input."""
    pos = 0

    def u():
        nonlocal pos
        v, pos = read_uvarint(buf, pos)
        return v

    def take(n):
        nonlocal pos
        if n < 0 or pos + n > len(buf):
            raise ValueError("truncated")
        b = buf[pos:pos + n]
        pos += n
        return b

    def bounded(n, lim):
        if n > lim:
            raise ValueError("count over limit")
        return n

    if take(1)[0] != 2:
        raise ValueError("version")
    flags = u()
    if flags & ~1:
        raise ValueError("unknown flags")
    install = str(uuidlib.UUID(bytes=take(16))) if flags & 1 else None
    first_seq, n = u(), bounded(u(), 10000)
    gaps = {}
    for _ in range(bounded(u(), n)):
        i = u()
        gaps[i] = u()
    seqs, s = [], first_seq
    for i in range(n):
        s += gaps.get(i, 0) + (1 if i else 0)
        seqs.append(s)
    base = u()
    sent_delta = unzz(u())
    strs = [take(u()).decode() for _ in range(bounded(u(), 65536))]
    uuids = [str(uuidlib.UUID(bytes=take(16))) for _ in range(bounded(u(), 65536))]
    hexes = [take(u()).hex() for _ in range(bounded(u(), 65536))]
    project, sdk_name, sdk_version = strs[u()], strs[u()], strs[u()]
    ctxs = []
    for _ in range(bounded(u(), n)):
        if take(1)[0] == 1:
            ctxs.append(ctx_cache[take(8)])
            continue
        sess = str(uuidlib.UUID(bytes=take(16)))
        vals = [strs[u()] for _ in CTX_FIELDS[:-1]] + [unzz(u())]
        ctxs.append((sess, *vals))
        if ctx_cache is not None:
            ctx_cache[_fp(b"C" + uuidlib.UUID(sess).bytes + jdump(vals).encode())] = ctxs[-1]
    shapes = []
    for _ in range(bounded(u(), n)):
        if take(1)[0] == 1:
            shapes.append(shape_cache[take(8)])
            continue
        name = strs[u()]
        fields = []
        for _ in range(bounded(u(), 32)):
            k = strs[u()]
            t = take(1)[0]
            fields.append((k, (T_ALIAS, u()) if t == T_ALIAS else t))
        shapes.append((name, fields))
        if shape_cache is not None:
            shape_cache[_shape_fp(name, fields)] = shapes[-1]
    coldir = []
    for _ in range(bounded(u(), 4096)):
        k, t = strs[u()], take(1)[0]
        mode = take(1)[0] if t == T_INT else 0
        coldir.append((k, t, mode))
    shape_col = [u() for _ in range(n)]
    ctx_col = []
    while len(ctx_col) < n:
        v, r = u(), u()
        ctx_col.extend([v] * bounded(r, n - len(ctx_col)))
    dt_col = [unzz(u()) for _ in range(n)]
    el_col = [unzz(u()) for _ in range(n)]
    # count values per column from shapes
    need = {}
    for sid in shape_col:
        for k, t in shapes[sid][1]:
            if not isinstance(t, tuple) and t not in (T_CTXREF, T_NULL):
                need[(k, t)] = need.get((k, t), 0) + 1
    colvals = {}
    for k, t, mode in coldir:
        vals, p = [], 0
        for _ in range(need.get((k, t), 0)):
            if t == T_INT:
                v = unzz(u())
                if mode:
                    v += p
                    p = v
            elif t == T_STR:
                v = strs[u()]
            elif t == T_NUMTEXT:
                v = Decimal(strs[u()])
            elif t == T_U64:
                v = u()
            elif t == T_UUID:
                v = uuids[u()]
            elif t == T_HEX:
                v = hexes[u()]
            elif t == T_BOOL:
                v = bool(take(1)[0])
            elif t == T_F32:
                v = struct.unpack("<f", take(4))[0]
            elif t == T_F64:
                v = struct.unpack("<d", take(8))[0]
            else:
                raise ValueError("type")
            vals.append(v)
        colvals[(k, t)] = iter(vals)
    if pos != len(buf):
        raise ValueError("trailing bytes")
    events, ts, prev_el = [], base, {}
    for i in range(n):
        ts += dt_col[i]
        c = ctxs[ctx_col[i]]
        pe = prev_el.get(ctx_col[i])
        el = el_col[i] if pe is None else el_col[i] + pe[0] + ts - pe[1]
        prev_el[ctx_col[i]] = (el, ts)
        name, fields = shapes[shape_col[i]]
        ctxd = dict(zip(CTX_FIELDS, c[1:]))
        props, keys = {}, [k for k, _ in fields]
        for k, t in fields:
            if isinstance(t, tuple):
                props[k] = props[keys[t[1]]]
            elif t == T_CTXREF:
                props[k] = ctxd[k]
            elif t == T_NULL:
                props[k] = None
            else:
                props[k] = next(colvals[(k, t)])
        ev = {"session_id": c[0], "name": name, "ts": ts, "session_elapsed_ms": el, **ctxd,
              "properties": props, "sequence": seqs[i]}
        events.append(ev)
    last_ts = events[-1]["ts"] if events else base
    meta = {"install_id": install, "project_id": project, "sdk": {"name": sdk_name, "version": sdk_version},
            "sent_at_ms": last_ts + sent_delta}
    return meta, events
