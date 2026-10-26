#!/usr/bin/env python3
"""Offline estimate of the presence-mask idea for V8 (no protocol change, no device). Value columns are identical in both designs (they are keyed by key+kind already); only the
STRUCTURAL part of a packet differs, so we compare that part, compressed with zstd per packet of N events:
  current : per row a shape id (uvarint) - a shape is the exact set of typed keys of one event name
  mask    : per row the event-name id (uvarint) + a presence bitmask over that name's typed columns (key+kind, append-only in first-seen order; null is a kind with no data)
Also the size of the project catalog the server holds and every new install downloads (JSON, gzip) and the number of entries each design needs.
Usage: mask_estimate.py DATA_DIR [packet=200]   (jsonl files {"name","props"}; uses *_slice_00 and *_slice_01)"""
import gzip, json, sys, zstandard
from pathlib import Path
DIR = Path(sys.argv[1]); N = int(sys.argv[2]) if len(sys.argv) > 2 else 200
cz = zstandard.ZstdCompressor(level=3)
def kind(v):
    if v is None: return 'null'
    if isinstance(v, bool): return 'bool'
    if isinstance(v, int): return 'int'
    if isinstance(v, float): return 'double'
    return 'str'
def uvarint(n):
    out = bytearray()
    while True:
        b = n & 0x7f; n >>= 7
        if n: out.append(b | 0x80)
        else: out.append(b); return bytes(out)
def load(path, limit=3000):
    ev = []
    for line in open(path):
        o = json.loads(line)
        if len(o['props']) <= 32: ev.append((o['name'], tuple(sorted((k, kind(v)) for k, v in o['props'].items()))))
        if len(ev) >= limit: break
    return ev
def run(events):
    shape_ids = {}; names = {}; cols = {}          # shape key -> id ; name -> id ; name -> {column -> index}
    last_mask = {}
    bytes_r = 0
    per_event_s = per_event_m = 0
    bytes_s = bytes_m = 0
    for start in range(0, len(events) - N + 1, N):
        s_ids = bytearray(); n_ids = bytearray(); masks = bytearray(); flags = bytearray(); newmasks = bytearray()
        for name, fields in events[start:start + N]:
            sid = shape_ids.setdefault((name, fields), len(shape_ids)); s_ids += uvarint(sid)
            nid = names.setdefault(name, len(names)); n_ids += uvarint(nid)
            c = cols.setdefault(name, {})
            for f in fields: c.setdefault(f, len(c))
            width = (len(c) + 7) // 8; m = 0
            for f in fields: m |= 1 << c[f]
            masks += m.to_bytes(width, 'little')
            if last_mask.get(name) == m: flags.append(0)
            else: flags.append(1); newmasks += m.to_bytes(width, 'little'); last_mask[name] = m
        bytes_s += len(cz.compress(bytes(s_ids)))
        bytes_m += len(cz.compress(bytes(n_ids) + bytes(masks)))
        bytes_r += len(cz.compress(bytes(n_ids) + bytes(flags) + bytes(newmasks)))
        per_event_s += N; per_event_m += N
    cat_shapes = [{'n': n, 'f': [list(x) for x in fields]} for (n, fields) in shape_ids]
    cat_mask = [{'n': n, 'c': [list(x) for x in sorted(c, key=c.get)]} for n, c in cols.items()]
    gz = lambda o: len(gzip.compress(json.dumps(o, separators=(',', ':')).encode()))
    return dict(events=per_event_s, shapes=len(shape_ids), names=len(names), columns=sum(len(c) for c in cols.values()), structure_current=bytes_s / per_event_s, structure_mask=bytes_m / per_event_m, structure_refined=bytes_r / per_event_m,
                catalog_current=gz(cat_shapes), catalog_mask=gz(cat_mask), max_mask_bytes=max((len(c) + 7) // 8 for c in cols.values()))
print(f'packet = {N} events; structural bytes per event after zstd (value columns are the same in both designs)\n')
print(f"{'dataset':26} {'shapes':>7} {'names':>6} {'columns':>8} {'struct now':>11} {'mask plain':>11} {'mask+same-flag':>15} {'catalog now':>12} {'catalog mask':>13} {'mask bytes':>10}")
for pattern in ('*_slice_00.jsonl',):
    for f in sorted(DIR.glob(pattern)):
        r = run(load(f))
        print(f"{f.stem:26} {r['shapes']:7} {r['names']:6} {r['columns']:8} {r['structure_current']:11.2f} {r['structure_mask']:11.2f} {r['structure_refined']:15.2f} {r['catalog_current']:12} {r['catalog_mask']:13} {r['max_mask_bytes']:10}")
