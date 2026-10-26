"""MTB6 research reference. Registered schemas and immutable context aliases.
Python allocates; only the separately measured C integer kernel is allocation-free.
"""
import copy, hashlib, json, math, secrets, struct, uuid, zlib
from decimal import Decimal
from datetime import datetime
from types import SimpleNamespace
import zstandard as z
from support import core, wire, exact, Reader, u, zz, packbits, readbits

MAX_RAW = 2097152
MAX_FRAME = 262144
CTX = ('session_id', *wire.DEVICE_KEYS)
REF_CTX, REF_PROP = 12, 13

def dump(x):
    return json.dumps(x, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode()

def blob(b):
    return u(len(b)) + b

def takeblob(r):
    return r.take(r.count(MAX_RAW))

def integers(xs):
    if not xs:
        return b''
    direct = [int(v) for v in xs]
    delta = [direct[0]] + [b-a for a, b in zip(direct, direct[1:])]
    opts = []
    for mode, vs in enumerate((direct, delta)):
        if any(not -(1 << 63) <= v < (1 << 63) for v in vs):
            continue
        opts.append(bytes([mode]) + b''.join(u(zz(v)) for v in vs))
        lo = min(vs)
        width = (max(vs)-lo).bit_length()
        opts.append(bytes([mode+2]) + u(zz(lo)) + bytes([width]) + packbits([v-lo for v in vs], width))
    if not opts:
        raise ValueError('integer domain')
    return min(opts, key=len)

def readintegers(r, n):
    if not n:
        return []
    mode = r.byte()
    if mode in (0, 1):
        out = [r.s() for _ in range(n)]
    elif mode in (2, 3):
        lo = r.s()
        out = [lo+x for x in readbits(r, n, r.byte())]
    else:
        raise ValueError('integer mode')
    if mode in (1, 3):
        total = 0
        for i, v in enumerate(out):
            total += v
            out[i] = total
    if any(not -(1 << 63) <= v < (1 << 63) for v in out):
        raise ValueError('integer range')
    return out

def shape(e):
    fields = []
    p = e['properties']
    for k, v in p.items():
        t = core._vtype(v)
        if k in wire.DEVICE_KEYS and type(v) is type(e[k]) and wire.jdump(v) == wire.jdump(e[k]):
            t = REF_CTX
        elif k == 'wave_attempt_id' and type(v) is str and v == p.get('attempt_id') and 'attempt_id' in list(p)[:len(fields)]:
            t = REF_PROP
        fields.append((k, t))
    return (e['name'], tuple(fields))

def validate_schema(shapes):
    if not isinstance(shapes, list) or len(shapes) > 16000:
        raise ValueError('schema count')
    out = []
    for entry in shapes:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise ValueError('schema entry')
        name, fields = entry
        if type(name) is not str or not 1 <= len(name) <= 64 or not isinstance(fields, (list, tuple)) or len(fields) > 32:
            raise ValueError('schema fields')
        seen = set()
        for k, t in fields:
            if type(k) is not str or not 1 <= len(k) <= 64 or k in seen or type(t) is not int or t not in (*range(8), 10, 11, REF_CTX, REF_PROP):
                raise ValueError('schema field')
            if t == REF_CTX and k not in wire.DEVICE_KEYS:
                raise ValueError('context reference')
            if t == REF_PROP and (k != 'wave_attempt_id' or 'attempt_id' not in seen):
                raise ValueError('property reference')
            seen.add(k)
        out.append((name, tuple(tuple(f) for f in fields)))
    if len(set(out)) != len(out):
        raise ValueError('duplicate shape')
    return out

class Schema:
    def __init__(self, shapes):
        self.shapes = validate_schema(list(shapes))
        self.data = dump(self.shapes)
        self.id = hashlib.sha256(self.data).digest()[:8]
        self.ids = {s: i for i, s in enumerate(self.shapes)}

    @classmethod
    def train(cls, dataset):
        shapes = set(shape(e) for _, bs in dataset for b in bs for e in b)
        return cls(sorted(shapes))

class Aliases:
    """Server-authorized immutable records; never reuse a slot within an epoch."""
    def __init__(self, epoch=None):
        self.records = []
        self.ids = {}
        self.epoch = secrets.token_bytes(8) if epoch is None else epoch
        if len(self.epoch) != 8:
            raise ValueError('alias epoch size')

    def register(self, origin, events):
        added = []
        for e in events:
            record = (origin, *(e[k] for k in CTX))
            if record not in self.ids:
                self.ids[record] = len(self.records)
                self.records.append(record)
                added.append(record)
        # Actual counted request+response: first slot, records, then returned slots.
        payload = dump([len(self.records)-len(added), added])
        return self.epoch+z.ZstdCompressor(level=1).compress(payload) if added else b''

    def accept(self, payload):
        if not 9 <= len(payload) <= MAX_FRAME or (self.records and payload[:8] != self.epoch):
            raise ValueError('alias epoch')
        params = z.get_frame_parameters(payload[8:])
        if params.window_size > MAX_RAW or (params.content_size != z.CONTENTSIZE_UNKNOWN and params.content_size > MAX_RAW):
            raise ValueError('registration size/window')
        data = z.ZstdDecompressor().decompress(payload[8:], max_output_size=MAX_RAW, allow_extra_data=False)
        if len(data) > MAX_RAW:
            raise ValueError('registration size')
        first, records = json.loads(data)
        if type(first) is not int or first != len(self.records) or not isinstance(records, list):
            raise ValueError('alias sequence')
        pending = []
        for record in records:
            if not isinstance(record, list) or len(record) != len(CTX)+1:
                raise ValueError('alias record')
            if any(type(v) is not str for v in record[:-1]) or type(record[-1]) is not int:
                raise ValueError('alias types')
            for v in record[:2]:
                if str(uuid.UUID(v)) != v:
                    raise ValueError('alias uuid')
            pending.append(tuple(record))
        if len(self.records)+len(pending) > 65536 or any(r in self.ids for r in pending) or len(set(pending)) != len(pending):
            raise ValueError('alias duplicate/limit')
        for record in pending:
            self.ids[record] = len(self.records)
            self.records.append(record)
        self.epoch = payload[:8]

def enc_values(t, values):
    if t == core.T_INT:
        return integers(values)
    if t == core.T_U64:
        return b''.join(u(v) for v in values)
    if t == core.T_BOOL:
        return packbits([int(v) for v in values], 1)
    if t in (core.T_F32, core.T_F64):
        fmt = '<f' if t == core.T_F32 else '<d'
        raw = b'\x00' + b''.join(struct.pack(fmt, v) for v in values)
        scaled = []
        for v in values:
            if not math.isfinite(v*100) or abs(v*100) >= (1 << 63):
                return raw
            m = round(v*100)
            # Scale only when the original IEEE bits, including signed zero, return exactly.
            if struct.pack(fmt, m/100) != struct.pack(fmt, v):
                return raw
            scaled.append(m)
        return min((raw, b'\x01'+integers(scaled)), key=len)
    if t == core.T_NULL:
        return b''
    unique = list(dict.fromkeys(str(v) if t == core.T_NUMTEXT else v for v in values))
    ids = {v: i for i, v in enumerate(unique)}
    encoded = bytearray(u(len(unique)))
    for v in unique:
        if t == core.T_UUID:
            encoded += uuid.UUID(v).bytes
        elif t == core.T_HEX:
            encoded += blob(bytes.fromhex(v))
        else:
            encoded += blob(v.encode('utf-8', errors='surrogatepass'))
    return bytes(encoded) + integers([ids[str(v) if t == core.T_NUMTEXT else v] for v in values])

def dec_values(r, t, n):
    if t == core.T_INT:
        return readintegers(r, n)
    if t == core.T_U64:
        return [r.u() for _ in range(n)]
    if t == core.T_BOOL:
        return [bool(v) for v in readbits(r, n, 1)]
    if t in (core.T_F32, core.T_F64):
        fmt, size = ('<f', 4) if t == core.T_F32 else ('<d', 8)
        mode = r.byte()
        if mode == 0:
            values = [struct.unpack(fmt, r.take(size))[0] for _ in range(n)]
        elif mode == 1:
            values = [struct.unpack(fmt, struct.pack(fmt, v/100))[0] for v in readintegers(r, n)]
        else:
            raise ValueError('float mode')
        if not all(math.isfinite(v) for v in values):
            raise ValueError('nonfinite')
        return values
    if t == core.T_NULL:
        return [None]*n
    unique = []
    for _ in range(r.count(n)):
        if t == core.T_UUID:
            v = str(uuid.UUID(bytes=r.take(16)))
        elif t == core.T_HEX:
            v = takeblob(r).hex()
        else:
            v = takeblob(r).decode('utf-8', errors='surrogatepass')
            if t == core.T_NUMTEXT:
                v = Decimal(v)
                if not v.is_finite():
                    raise ValueError('decimal')
        unique.append(v)
    indices = readintegers(r, n)
    if any(not 0 <= i < len(unique) for i in indices):
        raise ValueError('value index')
    return [unique[i] for i in indices]

def encode_raw(schema, aliases, origin, batch, *, replay=False, preserve_ids=False, masks=False):
    if not 1 <= len(batch) <= 500:
        raise ValueError('events')
    shapes = list(schema.shapes)
    ids = dict(schema.ids)
    extras = []
    shape_ids, context_ids, elapsed = [], [], []
    previous = {}
    for e in batch:
        s = shape(e)
        if s not in ids:
            ids[s] = len(shapes)
            shapes.append(s)
            extras.append(s)
        shape_ids.append(ids[s])
        context_ids.append(aliases.ids[(origin, *(e[k] for k in CTX))])
        sid = e['session_id']
        pe = previous.get(sid)
        elapsed.append(e['session_elapsed_ms'] if pe is None else e['session_elapsed_ms']-pe[0]-e['ts']+pe[1])
        previous[sid] = (e['session_elapsed_ms'], e['ts'])
    out = bytearray(blob(dump(extras)))
    streams = ([e['sequence'] for e in batch], [e['ts'] for e in batch], elapsed, shape_ids, context_ids)
    for values in streams:
        out += integers(values)
    if preserve_ids:
        out += b''.join(uuid.UUID(e['event_id']).bytes for e in batch)
    if masks:
        # Explicit presence-mask ablation: precompiled shapes already imply these masks.
        keys = sorted({k for _, fields in shapes for k, _ in fields})
        for e in batch:
            out += int(sum(1 << keys.index(k) for k in e['properties'])).to_bytes((len(keys)+7)//8, 'little')
    cols = {}
    hash_last = None
    for e, sid in zip(batch, shape_ids):
        for k, t in shapes[sid][1]:
            if t in (REF_CTX, REF_PROP):
                continue
            value = e['properties'][k]
            if replay and k == 'placed_state_hash' and t == core.T_HEX and len(value) == 64:
                predicted = core.hash_prediction(hash_last, e)
                hash_last = value
                value = '=' if predicted == value else value
                t = 14
            cols.setdefault((k, t), []).append(value)
    # Column order is first appearance in the event stream, including all mixed types.
    for (k, t), values in cols.items():
        if t == 14:
            out += packbits([int(v == '=') for v in values], 1)
            out += b''.join(bytes.fromhex(v) for v in values if v != '=')
        else:
            out += enc_values(t, values)
    if len(out) > MAX_RAW:
        raise ValueError('raw limit')
    return bytes(out)

def decode_raw(schema, aliases, raw, n, flags):
    r = Reader(raw)
    extras = validate_schema(json.loads(takeblob(r)))
    if any(s in schema.ids for s in extras):
        raise ValueError('duplicate extension')
    shapes = schema.shapes+extras
    sequences, times, elapsed, sids, cids = [readintegers(r, n) for _ in range(5)]
    if any(not 0 <= s < len(shapes) for s in sids) or any(not 0 <= c < len(aliases.records) for c in cids):
        raise ValueError('unregistered reference')
    event_ids = [str(uuid.UUID(bytes=r.take(16))) for _ in range(n)] if flags & 2 else [None]*n
    maskkeys = sorted({k for _, fields in shapes for k, _ in fields}) if flags & 4 else []
    masks = [int.from_bytes(r.take((len(maskkeys)+7)//8), 'little') for _ in range(n)] if flags & 4 else None
    events, cols, previous = [], {}, {}
    origin = None
    for i in range(n):
        record = aliases.records[cids[i]]
        if origin is not None and origin != record[0]:
            raise ValueError('mixed origin')
        origin = record[0]
        e = dict(zip(CTX, record[1:]))
        name, fields = shapes[sids[i]]
        sid = e['session_id']
        pe = previous.get(sid)
        el = elapsed[i] if pe is None else elapsed[i]+pe[0]+times[i]-pe[1]
        previous[sid] = (el, times[i])
        e.update(name=name, ts=times[i], sequence=sequences[i], session_elapsed_ms=el, properties={})
        if event_ids[i] is not None:
            e['event_id'] = event_ids[i]
        if masks is not None and masks[i] != sum(1 << maskkeys.index(k) for k, _ in fields):
            raise ValueError('presence mask')
        for k, t in fields:
            if t in (REF_CTX, REF_PROP):
                continue
            # A replay column covers only fixed 32-byte hashes; schema type HEX permits other lengths.
            if flags & 1 and k == 'placed_state_hash' and t == core.T_HEX:
                t = 14
            cols.setdefault((k, t), []).append(e)
        events.append(e)
    for (k, t), owners in cols.items():
        if t == 14:
            bits = readbits(r, len(owners), 1)
            values = ['=' if bit else r.take(32).hex() for bit in bits]
        else:
            values = dec_values(r, t, len(owners))
        for e, value in zip(owners, values):
            e['properties'][k] = value
    last = None
    for e, sid in zip(events, sids):
        p = e['properties']
        if flags & 1 and p.get('placed_state_hash') == '=':
            pred = core.hash_prediction(last, e)
            if pred is None:
                raise ValueError('hash without anchor')
            p['placed_state_hash'] = pred
        if type(p.get('placed_state_hash')) is str:
            last = p['placed_state_hash']
        ordered = {}
        for k, t in shapes[sid][1]:
            ordered[k] = e[k] if t == REF_CTX else ordered['attempt_id'] if t == REF_PROP else p[k]
        e['properties'] = ordered
    r.end()
    if any(not 1 <= e['sequence'] < (1 << 63) for e in events) or any(a >= b for a, b in zip(sequences, sequences[1:])):
        raise ValueError('sequences')
    return origin, events

def render(origin, events, preserve_ids=False):
    inst = SimpleNamespace(install_id=origin)
    try:
        return wire.v1_json(inst, events, not preserve_ids)
    except UnicodeEncodeError:
        obj = wire._v1_obj(inst, events)
        if not preserve_ids:
            for e in obj['events']:
                e.pop('event_id', None)
        return wire.jdump(obj).encode('utf-8', errors='backslashreplace')

def encode(schema, aliases, origin, batch, *, replay=False, preserve_ids=False, masks=False, level=1, source=None, lz4=False):
    flags = int(replay) | (int(preserve_ids) << 1) | (int(masks) << 2)
    if replay and any(k == 'placed_state_hash' and (type(v) is not str or len(v) != 64 or not wire.HEX_RE.fullmatch(v)) for e in batch for k, v in e['properties'].items()):
        raise ValueError('replay hash domain')
    raw = encode_raw(schema, aliases, origin, batch, replay=replay, preserve_ids=preserve_ids, masks=masks)
    canonical = render(origin, batch, preserve_ids)
    # Literal escape preserves noncanonical source bytes/sent_at/envelope fields without an expensive diff.
    if source is not None and source != canonical:
        raw, flags = source, 8
    if len(raw) > MAX_RAW:
        raise ValueError('source limit')
    if lz4:
        from lz4_block import compress
        comp = compress(raw)
    else:
        comp = z.ZstdCompressor(level=level).compress(raw)
    body, compression = (comp, 2 if lz4 else 1) if len(comp) < len(raw) else (raw, 0)
    frame = b'M6' + bytes([flags, compression]) + schema.id + aliases.epoch + u(len(batch)) + u(len(raw)) + body
    frame += struct.pack('<I', zlib.crc32(frame))
    if len(frame) > MAX_FRAME:
        raise ValueError('split/fallback')
    return frame

def decode(schema, aliases, frame, *, authorized_origin=None):
    if not 28 <= len(frame) <= MAX_FRAME or zlib.crc32(frame[:-4]) != int.from_bytes(frame[-4:], 'little'):
        raise ValueError('frame length/CRC')
    r = Reader(frame[:-4])
    if r.take(2) != b'M6':
        raise ValueError('magic')
    flags, compression = r.byte(), r.byte()
    if flags & ~15 or (flags & 8 and flags != 8) or compression not in (0, 1, 2) or r.take(8) != schema.id:
        raise ValueError('flags/schema')
    if r.take(8) != aliases.epoch:
        raise ValueError('alias epoch')
    n, size = r.count(500), r.count(MAX_RAW)
    if not n or not size:
        raise ValueError('empty')
    body = r.take(len(r.b)-r.p)
    if compression == 2:
        from lz4_block import decompress
        raw = decompress(body, size)
    elif compression == 1:
        try:
            params = z.get_frame_parameters(body)
            if params.window_size > MAX_RAW:
                raise ValueError('window')
            raw = z.ZstdDecompressor(max_window_size=MAX_RAW).decompress(body, max_output_size=size, allow_extra_data=False)
        except z.ZstdError as ex:
            raise ValueError('zstd') from ex
    else:
        raw = body
    if len(raw) != size:
        raise ValueError('raw size')
    if flags & 8:
        obj = json.loads(raw)
        if not isinstance(obj, dict) or len(obj.get('events', [])) != n:
            raise ValueError('literal shape')
        origin = obj.get('install_id')
        source = raw
    else:
        origin, events = decode_raw(schema, aliases, raw, n, flags)
        source = render(origin, events, bool(flags & 2))
    if authorized_origin is None or origin != authorized_origin:
        raise ValueError('origin authorization')
    # Reuse the audited V5 semantic limits at the server trust boundary.
    from frame_v5 import source_info
    info = source_info(source, origin, n)
    sent = info.get('sent_at_client')
    if type(sent) is not str or len(sent) != 24:
        raise ValueError('sent_at_client')
    datetime.strptime(sent, '%Y-%m-%dT%H:%M:%S.%fZ')
    for e in info['events']:
        if 'event_id' in e and (type(e['event_id']) is not str or str(uuid.UUID(e['event_id'])) != e['event_id']):
            raise ValueError('event uuid')
    return source
