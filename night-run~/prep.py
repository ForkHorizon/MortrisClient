"""Real 1M events -> catalog/dictionary trained on 20% of installs + SDK-format batches (100/batch, per install, by sequence)."""
import gzip, hashlib, json, sys, time
from collections import defaultdict
from datetime import datetime
from types import SimpleNamespace
EXP = '/Users/daliys/Daliys/UnityProjects/MortrisUnity/Assets/MortrisClient/Theory~/transport-v7/06-experiments'
sys.path.insert(0, EXP)
from support7 import wire
from transport7 import Catalog, Aliases, raw_encode
from bench7 import samples
from support7 import z
SRC = '/Users/daliys/Daliys/UnityProjects/MortrisUnity/Assets/MortrisClient/night-run~/work/puzzle-1m.jsonl.gz'
OUT = '/Users/daliys/Daliys/UnityProjects/MortrisUnity/Assets/MortrisClient/night-run~/work/'
t = time.time(); by = defaultdict(list); raw = defaultdict(list)
for line in gzip.open(SRC, 'rt'):
    e = json.loads(line.rstrip('\n').replace('\\\\', '\\'))
    ev = {k: e[k] for k in ('event_id', 'session_id', 'sequence', 'session_elapsed_ms', 'name', *wire.DEVICE_KEYS)}
    ev['properties'] = e['properties']; ev['ts'] = round(datetime.fromisoformat(e['occurred_at_client']).timestamp() * 1000)
    by[e['install_id']].append(ev); raw[e['install_id']].append(e)
train, hold = [], []
for origin, evs in sorted(by.items()):
    evs.sort(key=lambda x: x['sequence'])
    if len({x['sequence'] for x in evs}) != len(evs): continue
    ds = (SimpleNamespace(install_id=origin), [evs[i:i + 100] for i in range(0, len(evs), 100)])
    (train if int(hashlib.sha256(origin.encode()).hexdigest(), 16) % 5 == 0 else hold).append(ds)
print('train installs', len(train), 'events', sum(len(b) for _, bs in train for b in bs), 'hold installs', len(hold), 'events', sum(len(b) for _, bs in hold for b in bs), time.time() - t, flush=True)
c = Catalog.train('puzzle_gravity_test', train)
d = z.train_dictionary(16384, samples(c, train), level=1)
open(OUT + 'catalog.json', 'wb').write(c.data); open(OUT + 'dictionary.bin', 'wb').write(d.as_bytes())
print('catalog shapes', len(c.shapes), 'bytes', len(c.data), flush=True)
rawmap = {}
for origin, evs in raw.items():
    for e in evs: rawmap[e['event_id']] = e
from datetime import timezone
def iso(ms): return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (ms % 1000)
def sdk(e):
    r = rawmap[e['event_id']]
    return {'event_id': r['event_id'], 'session_id': r['session_id'], 'name': r['name'], 'occurred_at_client': iso(e['ts']), 'session_elapsed_ms': r['session_elapsed_ms'],
            'app_version': r['app_version'], 'build_number': r['build_number'], 'platform': r['platform'], 'os_version': r['os_version'], 'device_class': r['device_class'],
            'locale': r['locale'], 'timezone_offset_minutes': r['timezone_offset_minutes'], 'properties': r['properties'], 'sequence': r['sequence']}
n = 0
with open(OUT + 'batches.jsonl', 'w') as f:
    for split, ds in (('train', train), ('holdout', hold)):
        for inst, bs in ds:
            for b in bs:
                f.write(json.dumps({'split': split, 'origin': inst.install_id, 'events': [sdk(e) for e in b]}, ensure_ascii=True, separators=(',', ':')) + '\n'); n += len(b)
print('written events', n, time.time() - t)
