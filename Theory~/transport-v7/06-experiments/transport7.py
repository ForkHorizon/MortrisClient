"""Project-neutral research codec. Unknown schemas fail closed for V1 fallback.
Uses only V6's neutral typed-column, integer and context-alias primitives.
"""
import hashlib, json, math, re, struct, uuid, zlib
from decimal import Decimal
from datetime import datetime
from support7 import v6, core, Reader, u, z

MAX_RAW, MAX_FRAME = v6.MAX_RAW, v6.MAX_FRAME
Aliases = v6.Aliases

def shape(event, logical_strings=False):
    return event['name'], tuple(sorted((k, core.T_STR if logical_strings and type(v) is str else core._vtype(v)) for k, v in event['properties'].items()))

class Catalog:
    def __init__(self, project, shapes, logical_strings=False):
        if type(project) is not str or not 1 <= len(project.encode()) <= 128:
            raise ValueError('project')
        self.project = project
        if type(logical_strings) is not bool:
            raise ValueError('logical string policy')
        self.logical_strings = logical_strings
        self.shapes = v6.validate_schema([(name, sorted(fields)) for name, fields in shapes])
        if any(t in (12, 13) for _, fs in self.shapes for _, t in fs):
            raise ValueError('implicit references forbidden')
        names = sorted({s[0] for s in self.shapes})
        if len(names) > 255:
            raise ValueError('event enum overflow')
        keys = sorted({k for _, fs in self.shapes for k, _ in fs})
        self.events = {name: i + 1 for i, name in enumerate(names)}
        self.masks = [sum(1 << keys.index(k) for k, _ in fs) for _, fs in self.shapes]
        descriptor = {'project_id': project, 'events': self.events, 'keys': keys,
                      'shapes': self.shapes, 'masks': self.masks}
        if logical_strings:
            descriptor['logical_strings'] = True
        self.data = v6.dump(descriptor)
        self.id = hashlib.sha256(self.data).digest()[:8]
        self.ids = {s: i for i, s in enumerate(self.shapes)}

    @classmethod
    def train(cls, project, dataset, logical_strings=False):
        return cls(project, sorted({shape(e, logical_strings) for _, bs in dataset for b in bs for e in b}), logical_strings)

    def shape(self, event):
        return shape(event, self.logical_strings)

    @classmethod
    def load(cls, data):
        if not 1 <= len(data) <= MAX_RAW:
            raise ValueError('catalog size')
        obj = json.loads(data)
        result = cls(obj['project_id'], obj['shapes'], obj.get('logical_strings', False))
        if result.data != data:
            raise ValueError('noncanonical catalog')
        return result

def raw_encode(catalog, aliases, origin, batch, preserve_ids=True, integer_model=False, string_model=False, metadata_model=False):
    if not 1 <= len(batch) <= 500:
        raise ValueError('event count')
    sids, cids, elapsed, previous = [], [], [], {}
    columns, column_owners = {}, {}
    for e in batch:
        sid = catalog.ids[catalog.shape(e)]
        sids.append(sid)
        cids.append(aliases.ids[(origin, *(e[k] for k in v6.CTX))])
        session = e['session_id']
        pe = previous.get(session)
        elapsed.append(e['session_elapsed_ms'] if pe is None else e['session_elapsed_ms'] - pe[0] - e['ts'] + pe[1])
        previous[session] = e['session_elapsed_ms'], e['ts']
        for k, t in catalog.shapes[sid][1]:
            columns.setdefault((k, t), []).append(e['properties'][k])
            if integer_model and t == core.T_INT:
                column_owners.setdefault((k, t), []).append(e)
    out = bytearray()
    for values in ([e['sequence'] for e in batch], [e['ts'] for e in batch], elapsed, sids, cids):
        if metadata_model:
            import metadata7
            out += metadata7.encode(values)
        else:
            out += v6.integers(values)
    if preserve_ids:
        out += b''.join(uuid.UUID(e['event_id']).bytes for e in batch)
    for (k, t), values in columns.items():
        if integer_model and t == core.T_INT:
            import numeric7
            out += numeric7.encode(values, column_owners[(k, t)])
        elif string_model and t in (core.T_STR, core.T_NUMTEXT):
            import string7
            out += string7.encode(t, values)
        else:
            out += v6.enc_values(t, values)
    if len(out) > MAX_RAW:
        raise ValueError('raw limit')
    return bytes(out)

def raw_decode(catalog, aliases, raw, n, preserve_ids=True, integer_model=False, string_model=False, metadata_model=False):
    r = Reader(raw)
    if metadata_model:
        import metadata7
        streams = [metadata7.decode(r, n) for _ in range(5)]
    else:
        streams = [v6.readintegers(r, n) for _ in range(5)]
    sequences, times, elapsed, sids, cids = streams
    if any(not 0 <= s < len(catalog.shapes) for s in sids) or any(not 0 <= c < len(aliases.records) for c in cids):
        raise ValueError('unknown reference')
    ids = [str(uuid.UUID(bytes=r.take(16))) for _ in range(n)] if preserve_ids else [None] * n
    events, columns, previous, origins = [], {}, {}, set()
    for i, sid in enumerate(sids):
        record = aliases.records[cids[i]]
        origins.add(record[0])
        e = dict(zip(v6.CTX, record[1:]))
        pe = previous.get(e['session_id'])
        el = elapsed[i] if pe is None else elapsed[i] + pe[0] + times[i] - pe[1]
        previous[e['session_id']] = el, times[i]
        e.update(sequence=sequences[i], ts=times[i], session_elapsed_ms=el,
                 name=catalog.shapes[sid][0], properties={})
        if preserve_ids:
            e['event_id'] = ids[i]
        for k, t in catalog.shapes[sid][1]:
            columns.setdefault((k, t), []).append(e)
        events.append(e)
    for (k, t), owners in columns.items():
        if integer_model and t == core.T_INT:
            import numeric7
            values = numeric7.decode(r, len(owners), owners)
        elif string_model and t in (core.T_STR, core.T_NUMTEXT):
            import string7
            values = string7.decode(r, t, len(owners))
        else:
            values = v6.dec_values(r, t, len(owners))
        for e, value in zip(owners, values):
            e['properties'][k] = value
    for e, sid in zip(events, sids):
        e['properties'] = {k: e['properties'][k] for k, _ in catalog.shapes[sid][1]}
    r.end()
    if len(origins) != 1 or any(not 1 <= s < 1 << 63 for s in sequences) or any(a >= b for a, b in zip(sequences, sequences[1:])):
        raise ValueError('origin/sequence')
    return origins.pop(), events

def dict_id(dictionary):
    return hashlib.sha256(dictionary.as_bytes()).digest()[:8] if dictionary else bytes(8)

def encode(catalog, aliases, origin, batch, dictionary=None, preserve_ids=True, integer_model=False, string_model=False, metadata_model=False):
    raw = raw_encode(catalog, aliases, origin, batch, preserve_ids, integer_model, string_model, metadata_model)
    comp = z.ZstdCompressor(level=1, dict_data=dictionary).compress(raw)
    body, mode = (comp, 1) if len(comp) < len(raw) else (raw, 0)
    frame = b'M7' + bytes([int(preserve_ids) | (int(integer_model) << 1) | (int(string_model) << 2) | (int(metadata_model) << 4), mode]) + catalog.id + aliases.epoch + dict_id(dictionary) + u(len(batch)) + u(len(raw)) + body
    frame += struct.pack('<I', zlib.crc32(frame))
    if len(frame) > MAX_FRAME:
        raise ValueError('split/V1 fallback')
    return frame

def decode(catalog, aliases, frame, dictionary=None, *, authorized_project, authorized_origin):
    if catalog.project != authorized_project:
        raise ValueError('project authorization')
    if not 36 <= len(frame) <= MAX_FRAME or zlib.crc32(frame[:-4]) != int.from_bytes(frame[-4:], 'little'):
        raise ValueError('frame length/CRC')
    r = Reader(frame[:-4])
    if r.take(2) != b'M7':
        raise ValueError('magic')
    flags, compression = r.byte(), r.byte()
    if flags & ~23 or compression > 1 or r.take(8) != catalog.id or r.take(8) != aliases.epoch or r.take(8) != dict_id(dictionary):
        raise ValueError('flags/catalog/epoch/dictionary')
    n, size = r.count(500), r.count(MAX_RAW)
    if not n or not size:
        raise ValueError('empty')
    body = r.take(len(r.b) - r.p)
    if compression:
        params = z.get_frame_parameters(body)
        if params.window_size > MAX_RAW or params.content_size != size:
            raise ValueError('zstd size/window')
        raw = z.ZstdDecompressor(dict_data=dictionary, max_window_size=MAX_RAW).decompress(body, max_output_size=size, allow_extra_data=False)
    else:
        raw = body
    if len(raw) != size:
        raise ValueError('raw size')
    origin, events = raw_decode(catalog, aliases, raw, n, bool(flags & 1), bool(flags & 2), bool(flags & 4), bool(flags & 16))
    if origin != authorized_origin:
        raise ValueError('origin authorization')
    validate_events(events)
    return origin, events


def validate_events(events):
    # Typed SDK boundary, independent of any game's envelope/project constants.
    pattern = r'[a-z](?:[a-z0-9]|_(?!_))*[a-z0-9]|[a-z]'
    for e in events:
        if not re.fullmatch(pattern, e['name']) or len(e['name']) > 64:
            raise ValueError('event name')
        datetime.fromtimestamp(e['ts'] / 1000)
        for k in v6.CTX[:-1]:
            if type(e[k]) is not str:
                raise ValueError('context type')
        if not -(1 << 63) <= e['session_elapsed_ms'] < 1 << 63 or not -(1 << 31) <= e[v6.CTX[-1]] < 1 << 31:
            raise ValueError('context range')
        p = e['properties']
        if len(p) > 32:
            raise ValueError('property count')
        size = 2
        for k, value in p.items():
            if len(k) > 64 or not re.fullmatch(pattern, k):
                raise ValueError('property key')
            if type(value) is str:
                if len(value.encode('utf-8', errors='replace')) > 1024:
                    raise ValueError('property string')
                encoded = json.dumps(value, ensure_ascii=False)
            elif type(value) in (int, float, Decimal):
                if not Decimal(str(value)).is_finite() or abs(Decimal(str(value))) > Decimal('1.7976931348623157e308'):
                    raise ValueError('property number')
                encoded = str(value)
            elif value is None or type(value) is bool:
                encoded = json.dumps(value)
            else:
                raise ValueError('property type')
            for char in ('<', '>', '&', '\u2028', '\u2029'):
                encoded = encoded.replace(char, '\\u%04x' % ord(char))
            size += len(json.dumps(k).encode()) + len(encoded.encode('utf-8', errors='backslashreplace')) + 2
        if size > 8193:  # Sum counts one extra separator relative to a nonempty JSON object.
            raise ValueError('property bytes')
