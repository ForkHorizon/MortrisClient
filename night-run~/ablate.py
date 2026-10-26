"""Which properties cost the most bytes in V7? Python reference encoder, catalog+dictionary retrained for each variant.
Train = installs with sha256%100<25, test = first 12 installs with sha256%100>=50. Variants: baseline, drop each property key, drop all UUID-valued properties, drop all strings."""
import gzip, hashlib, json, sys, time, copy
from types import SimpleNamespace
from datetime import datetime
EXP = '/Users/daliys/Daliys/UnityProjects/MortrisUnity/Assets/MortrisClient/Theory~/transport-v7/06-experiments'
sys.path.insert(0, EXP)
from support7 import wire, z
from transport7 import Catalog, Aliases, encode, shape
from bench7 import samples
W = '/Users/daliys/Daliys/UnityProjects/MortrisUnity/Assets/MortrisClient/night-run~/work/'
by = {}
for line in gzip.open(W + 'puzzle-1m.jsonl.gz', 'rt'):
    e = json.loads(line.rstrip('\n').replace('\\\\', '\\'))
    ev = {k: e[k] for k in ('event_id', 'session_id', 'sequence', 'session_elapsed_ms', 'name', *wire.DEVICE_KEYS)}
    ev['properties'] = e['properties']; ev['ts'] = round(datetime.fromisoformat(e['occurred_at_client']).timestamp() * 1000)
    by.setdefault(e['install_id'], []).append(ev)
def h(o): return int(hashlib.sha256(o.encode()).hexdigest(), 16) % 100
ids = sorted(o for o in by if h(o) < 25 or h(o) >= 50)
train_ids = [o for o in ids if h(o) < 25]; test_ids = [o for o in ids if h(o) >= 50][:12]
def ds(os_, drop=None):
    out = []
    for o in os_:
        evs = sorted(by[o], key=lambda x: x['sequence'])
        if drop: evs = [dict(e, properties={k: v for k, v in e['properties'].items() if not drop(k, v)}) for e in evs]
        out.append((SimpleNamespace(install_id=o), [evs[i:i + 100] for i in range(0, len(evs), 100)]))
    return out
def measure(drop):
    tr, te = ds(train_ids, drop), ds(test_ids, drop)
    c = Catalog.train('puzzle_gravity_test', tr); d = z.train_dictionary(16384, samples(c, tr), level=1)
    total = n = miss = 0
    for inst, bs in te:
        a = Aliases(bytes(8))
        for b in bs:
            if any(shape(e) not in c.ids for e in b): miss += len(b); continue
            a.register(inst.install_id, b); f = encode(c, a, inst.install_id, b, d, False); total += len(f); n += len(b)
    return total / max(n, 1), n, miss
import re
UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
keys = sorted({k for o in train_ids for e in by[o] for k in e['properties']})
res = {}
t0 = time.time(); base, n, miss = measure(None); res['__baseline__'] = {'bytes_per_event': base, 'events': n, 'fallback': miss}; print('baseline', base, n, miss, time.time() - t0, flush=True)
variants = [('__no_uuid_strings__', lambda k, v: isinstance(v, str) and bool(UUID.match(v))), ('__no_strings__', lambda k, v: isinstance(v, str)), ('__no_ints__', lambda k, v: isinstance(v, int) and not isinstance(v, bool)), ('__no_bools__', lambda k, v: isinstance(v, bool))]
variants += [(k, (lambda kk: (lambda key, v: key == kk))(k)) for k in keys]
for name, fn in variants:
    b, n, miss = measure(fn); res[name] = {'bytes_per_event': b, 'saving_vs_baseline': base - b, 'events': n, 'fallback': miss}
    print(name, round(b, 3), 'saving', round(base - b, 3), flush=True)
    json.dump(res, open('results/data/ablation.json', 'w'), indent=1)
print('done', time.time() - t0)
