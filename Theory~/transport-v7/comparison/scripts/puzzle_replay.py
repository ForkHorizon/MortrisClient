"""De-identified Puzzle (all_clean) replay: builds harness/replay-private/puzzle_clean.jsonl and sizes before/after de-identification.
PRIVATE inputs: needs V7_EXP = a COPY of 06-experiments with results/private/puzzle-2026-10-16.jsonl.gz (see reproduce.sh; never point at frozen results,
real_data.load() writes real-audit.json). Output replay contains no real ids; it is still private (not committed).
De-identification: UUIDs, inventory_group_id, install/session/event ids -> consistent random values of identical format/length/cardinality;
placed_block_ids CSV tokens -> consistent random bijection of the observed integers; timestamps shifted by a constant. Integers and low-cardinality enums kept."""
import copy, gzip, json, os, random, re, sys, uuid
from pathlib import Path
from types import SimpleNamespace
EXP = Path(os.environ['V7_EXP']); sys.path.insert(0, str(EXP))
HERE = Path(__file__).resolve().parent; OUT = HERE.parent
from support7 import canonical_source, project_source, z, v6
from transport7 import Catalog, Aliases, encode, decode, shape, raw_encode
from real_data import load
from game_cleanup import cleaned
UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
rng = random.Random(7771); MAP = {}
def remap(kind, v, fn):
    k = (kind, v)
    if k not in MAP: MAP[k] = fn()
    return MAP[k]
def rid(v):
    if UUID.match(v): return remap('u', v, lambda: str(uuid.UUID(int=rng.getrandbits(128), version=4)))
    return remap('s', v, lambda: ''.join(rng.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in v))
INTS = {}
def deid_csv(s):
    out = []
    for t in s.split(','):
        if t.isdigit(): out.append(str(remap('i', t, lambda: rng.randrange(10 ** (len(t) - 1) if len(t) > 1 else 0, 10 ** len(t)))))
        else: out.append(t)
    return ','.join(out)
KEEP_STR = {'app_version', 'checkpoint_trigger', 'close_reason', 'coordinate_space', 'outcome', 'origin', 'progress_origin', 'rule_state'}
def deid_event(e, shift):
    e = copy.deepcopy(e)
    for k in ('event_id', 'session_id'): e[k] = rid(e[k])
    e['ts'] -= shift
    p = e['properties']
    for k, v in list(p.items()):
        if isinstance(v, str) and k not in KEEP_STR and v != '':
            p[k] = deid_csv(v) if k == 'placed_block_ids' else rid(v)
        if k == 'placed_state_hash': p[k] = rid(v) if isinstance(v, str) else v
    return e
def sizes(c, d32, ds):
    t = dict(v1_json=0, v1_gzip1=0, v7_seq=0, v7_full_uuid=0); n = fb = 0
    for inst, bs in ds:
        a, srv = Aliases(bytes(8)), Aliases(bytes(8))
        for b in bs:
            src = project_source(c.project, inst.install_id, b, True); gz = len(gzip.compress(src, 1, mtime=0)); n += len(b); t['v1_json'] += len(src); t['v1_gzip1'] += gz
            pl = a.register(inst.install_id, b)
            if pl: srv.accept(pl)
            if any(shape(e) not in c.ids for e in b): fb += len(b); t['v7_seq'] += gz; t['v7_full_uuid'] += gz; continue
            for key, full in (('v7_seq', False), ('v7_full_uuid', True)):
                f = encode(c, a, inst.install_id, b, d32, full); o, ev = decode(c, srv, f, d32, authorized_project=c.project, authorized_origin=inst.install_id)
                assert canonical_source(o, ev, full) == canonical_source(inst.install_id, b, full); t[key] += len(f)
    return dict(events=n, fallback_events=fb, bytes=t, B_event={k: v / n for k, v in t.items()})
def main():
    train, test = load(); tr = cleaned(train, migrate_interactions=True); te = cleaned(test, migrate_interactions=True)
    c = Catalog.train('puzzle_gravity_test', tr)
    samples = []
    for inst, bs in tr:
        a = Aliases(bytes(8))
        for b in bs: a.register(inst.install_id, b); samples.append(raw_encode(c, a, inst.install_id, b, False))
    d32 = z.train_dictionary(32768, samples, level=1)
    pick = [(inst, [bs[0][:100]]) for inst, bs in te if bs and len(bs[0]) >= 100][:6]
    shift = min(e['ts'] for _, bs in pick for e in bs[0]) - 1_700_000_000_000
    anon = [(SimpleNamespace(install_id=rid(inst.install_id)), [[deid_event(e, shift) for e in bs[0]]]) for inst, bs in pick]
    res = dict(source='puzzle-2026-10-16 all_clean holdout, first 100 events of first 6 installs (600 events)', catalog_bytes=len(c.data), dict_bytes=32768,
               original=sizes(c, d32, pick), deidentified=sizes(c, d32, anon))
    (OUT / 'harness' / 'replay-private').mkdir(exist_ok=True)
    with open(OUT / 'harness' / 'replay-private' / 'puzzle_clean.jsonl', 'w') as f:
        for _, bs in anon:
            for e in bs[0]: f.write(json.dumps({'name': e['name'], 'props': e['properties']}, separators=(',', ':')) + '\n')
    (OUT / 'results' / 'puzzle-replay-sizes.json').write_text(json.dumps(res, indent=1)); print(json.dumps(res, indent=1))
main()
