"""Learning-curve datasets: holdout = installs with sha256%100>=50. Catalog+dictionary trained on installs with h<2,5,10,25,50. Also holdout re-batched at 10/30 events."""
import gzip, hashlib, json, sys, time
from types import SimpleNamespace
from datetime import datetime, timezone
EXP = '/Users/daliys/Daliys/UnityProjects/MortrisUnity/Assets/MortrisClient/Theory~/transport-v7/06-experiments'
sys.path.insert(0, EXP)
from support7 import wire, z
from transport7 import Catalog
from bench7 import samples
W = '/Users/daliys/Daliys/UnityProjects/MortrisUnity/Assets/MortrisClient/night-run~/work/'
t = time.time(); by = {}; raw = {}
for line in gzip.open(W + 'puzzle-1m.jsonl.gz', 'rt'):
    e = json.loads(line.rstrip('\n').replace('\\\\', '\\'))
    ev = {k: e[k] for k in ('event_id', 'session_id', 'sequence', 'session_elapsed_ms', 'name', *wire.DEVICE_KEYS)}
    ev['properties'] = e['properties']; ev['ts'] = round(datetime.fromisoformat(e['occurred_at_client']).timestamp() * 1000)
    by.setdefault(e['install_id'], []).append(ev); raw[e['event_id']] = e
def h(o): return int(hashlib.sha256(o.encode()).hexdigest(), 16) % 100
ds = {}
for o, evs in sorted(by.items()):
    evs.sort(key=lambda x: x['sequence'])
    if len({x['sequence'] for x in evs}) != len(evs): continue
    ds[o] = evs
def iso(ms): return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (ms % 1000)
def sdk(e):
    r = raw[e['event_id']]
    return {'event_id': r['event_id'], 'session_id': r['session_id'], 'name': r['name'], 'occurred_at_client': iso(e['ts']), 'session_elapsed_ms': r['session_elapsed_ms'], 'app_version': r['app_version'],
            'build_number': r['build_number'], 'platform': r['platform'], 'os_version': r['os_version'], 'device_class': r['device_class'], 'locale': r['locale'],
            'timezone_offset_minutes': r['timezone_offset_minutes'], 'properties': r['properties'], 'sequence': r['sequence']}
hold = [o for o in ds if h(o) >= 50]
print('holdout installs', len(hold), 'events', sum(len(ds[o]) for o in hold), flush=True)
for size in (100, 30, 10):
    with open(W + f'lc_holdout_b{size}.jsonl', 'w') as f:
        for o in hold:
            for i in range(0, len(ds[o]), size):
                f.write(json.dumps({'split': 'holdout', 'origin': o, 'events': [sdk(e) for e in ds[o][i:i + size]]}, ensure_ascii=True, separators=(',', ':')) + '\n')
    print('wrote batch size', size, time.time() - t, flush=True)
for pct in (2, 5, 10, 25, 50):
    tr = [(SimpleNamespace(install_id=o), [ds[o][i:i + 100] for i in range(0, len(ds[o]), 100)]) for o in ds if h(o) < pct]
    n = sum(len(b) for _, bs in tr for b in bs)
    c = Catalog.train('puzzle_gravity_test', tr); d = z.train_dictionary(16384, samples(c, tr), level=1)
    open(W + f'lc_catalog_{pct}.json', 'wb').write(c.data); open(W + f'lc_dict_{pct}.bin', 'wb').write(d.as_bytes())
    print('catalog', pct, 'installs', len(tr), 'events', n, 'shapes', len(c.shapes), time.time() - t, flush=True)
