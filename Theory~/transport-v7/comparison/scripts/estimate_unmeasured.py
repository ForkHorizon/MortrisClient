"""Offline size models, NOT Firebase SDK capture or whole-HyperKit measurement.

Run from any directory. Reads private replay, emits aggregate sizes only.
HyperKit Gamestoty envelope mirrors local 1.5.14 Java source with synthetic values.
Firebase proxy uses an assumed protobuf layout, not Google's recovered schema.
"""
import gzip
import hashlib
import json
import random
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / 'harness/replay-private/puzzle_clean.jsonl'
HYPER = Path('/Users/daliys/Daliys/UnityProjects/Puzzle/Library/PackageCache/com.hypercell.hyperkit@01f716126add')


def varint(n):
    n &= (1 << 64) - 1
    out = bytearray()
    while n > 127:
        out.append((n & 127) | 128)
        n >>= 7
    return bytes(out + bytes([n]))


def field(tag, value):
    return varint(tag * 8 + 2) + varint(len(value)) + value


def compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode()


def proxy_event(row, index, truncate=False):
    out = field(1, row['name'].encode()) + varint(16) + varint(1700000000000 + index * 100)
    props = list(row['props'].items())
    if truncate:
        props = props[:25]
    for key, value in props:
        p = field(1, key.encode())
        if isinstance(value, str):
            p += field(2, (value[:100] if truncate else value).encode())
        elif isinstance(value, bool):
            p += field(2, str(value).lower().encode())
        elif isinstance(value, int):
            p += varint(24) + varint(value)
        elif isinstance(value, float):
            p += varint(33) + struct.pack('<d', value)
        else:
            raise ValueError('Unsupported proxy input type')
        out += field(3, p)
    return out


def main():
    assert varint(127) == b'\x7f' and varint(128) == b'\x80\x01'
    assert field(1, b'x') == b'\x0a\x01x'
    rows = [json.loads(x) for x in REPLAY.read_text().splitlines() if x]
    variants = []
    for device_len, idfa_len, os_len, source_len, campaign_len in [(10, 0, 10, 0, 0), (32, 36, 50, 20, 50)]:
        e = dict(event='level_start', level=12, stage=0, context='', app_ver='1.1.14',
                 device='D' * device_len, device_id='d' * 32, device_idfa='a' * idfa_len,
                 device_os='O' * os_len, ts_client='2026-10-18 12:00:00',
                 ts_client_local='2026-10-18 14:00:00', event_seq=1234,
                 event_id='e' * 16, sid='s' * 16, fps=[], source='S' * source_len,
                 campaign='C' * campaign_len, test=False)
        variants.append(len(compact([e])))
    models = []
    for truncate in (False, True):
        events = [proxy_event(r, i, truncate) for i, r in enumerate(rows)]
        for batch in (10, 100):
            for meta_bytes in (128, 512, 2048):
                rng = random.Random(20261018)
                raw = compressed = 0
                for start in range(0, len(events), batch):
                    # Deliberately incompressible assumed bundle metadata; sensitivity axis.
                    b = field(2, rng.randbytes(meta_bytes))
                    b += b''.join(field(1, ev) for ev in events[start:start + batch])
                    gz = gzip.compress(b, compresslevel=1, mtime=0)
                    assert gzip.decompress(gz) == b
                    raw += len(b)
                    compressed += len(gz)
                models.append(dict(truncated_strings_and_fields=truncate, batch=batch,
                                   assumed_metadata_bytes=meta_bytes, raw_B_event=raw / len(rows),
                                   assumed_gzip_B_event=compressed / len(rows)))
    paths = ['Runtime/SDK/Gamestoty/Plugins/Android/src/Gamestoty.java',
             'Runtime/Services/Analytics/Handlers/FirebaseEventBuilder.cs']
    out = dict(status='MODELED_NOT_MEASURED', events=len(rows),
               replay_sha256=hashlib.sha256(REPLAY.read_bytes()).hexdigest(),
               hyperkit_version='1.5.14', source_sha256={p: hashlib.sha256((HYPER / p).read_bytes()).hexdigest() for p in paths},
               gamestoty_basic_event_JSON_bytes=variants,
               firebase_proxy_warning='Assumed protobuf+gzip; not actual SDK schema/metadata, not an empirical bound.',
               firebase_proxy=models)
    (ROOT / 'results/code-size-estimates.json').write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
