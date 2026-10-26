"""Independent synthetic project (no Puzzle keys) V1 vs V7 sizes. Python reference encoder.
Frozen config: catalog + dict32 trained on TRAIN seeds only, level 1, sequence identity.
VALIDATION seeds are reported, TEST seeds were first run after this file was frozen.
Run (from anywhere): PYTHONDONTWRITEBYTECODE=1 <venv>/bin/python synth_bench.py
Python reference only: C# parity for real corpora is proven separately (native-frames); not re-proven for this synthetic set.
"""
import gzip, hashlib, json, random, sys, uuid
from pathlib import Path
from types import SimpleNamespace
HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1] / '06-experiments'
sys.path.insert(0, str(EXP))
from support7 import v6, z, canonical_source, rebatch
from transport7 import Catalog, Aliases, encode, decode, shape, raw_encode

PROJECT = 'synth_indie_runner'
NAMES = ['level_start', 'level_end', 'purchase_ui', 'ad_view', 'death', 'tutorial_step', 'sync']
DEV = [('android', '14', 'phone', 'en-US', -300), ('android', '13', 'phone', 'ru-RU', 180), ('ios', '17.2', 'phone', 'ja-JP', 540), ('android', '12', 'tablet', 'de-DE', 60)]
WORDS = ['光', 'Привет', 'naïve', '🙂', 'ß', 'longer title ' * 6]

def props(rng, profile, ix, name):
    p = {'level': rng.randint(1, 40), 'mode': rng.choice(['easy', 'hard', 'endless'])}
    if profile == 'low':
        p.update(score=rng.choice([0, 10, 50, 100, 250]), coins=rng.randint(0, 5), lucky=rng.random() < .1)
    else:  # high entropy: random floats, hex tokens, UUIDs, unicode
        p.update(score=rng.getrandbits(40), x=rng.uniform(-1e4, 1e4), y=rng.uniform(-1e4, 1e4), token=rng.randbytes(16).hex(),
                 ref=str(uuid.UUID(int=rng.getrandbits(128))), label=rng.choice(WORDS) + str(rng.getrandbits(20)))
        if ix % 11 == 0: p['blob'] = rng.randbytes(60).hex()
    if name == 'purchase_ui': p['sku'] = rng.choice(['gems_100', 'gems_500', 'noads']); p['price'] = rng.choice([0.99, 4.99, 9.99])
    return p

def corpus(profile, seed, installs, per_install, session_len):
    rng = random.Random(seed); out = []
    for j in range(installs):
        inst = SimpleNamespace(install_id=str(uuid.UUID(int=rng.getrandbits(128)))); dev = DEV[j % len(DEV)]
        ev = []; t = 1790000000000 + rng.randrange(10**7); sid = ''; left = 0; seq = 0; elapsed = 0
        for ix in range(per_install):
            if left == 0: sid = str(uuid.UUID(int=rng.getrandbits(128))); left = rng.randint(*session_len); elapsed = 0
            left -= 1; dt = rng.choice([40, 120, 900, 3000, 20000]); t += dt; elapsed += dt; seq += 1
            name = rng.choice(NAMES)
            ev.append(dict(event_id=str(uuid.UUID(int=rng.getrandbits(128))), session_id=sid, name=name, ts=t, session_elapsed_ms=elapsed,
                           app_version='1.4.' + str(j % 3), build_number='214', platform=dev[0], os_version=dev[1], device_class=dev[2],
                           locale=dev[3], timezone_offset_minutes=dev[4], properties=props(rng, profile, ix, name), sequence=seq))
        out.append((inst, [ev]))
    return out

def samples(c, ds):
    out = []
    for inst, bs in ds:
        a = Aliases(bytes(8))
        for b in bs:
            a.register(inst.install_id, b); out.append(raw_encode(c, a, inst.install_id, b, False))
    return out

def measure(c, d32, ds):
    t = dict(v1_json=0, v1_gzip1=0, v7_seq=0, v7_full_uuid=0); n = nb = setup = miss = 0; per = []
    for inst, bs in ds:
        a, srv = Aliases(bytes(8)), Aliases(bytes(8)); sb = 0; se = 0
        for b in bs:
            src = v6.render(inst.install_id, b, True); gz = len(gzip.compress(src, 1, mtime=0)); n += len(b); nb += 1; se += len(b)
            t['v1_json'] += len(src); t['v1_gzip1'] += gz
            pl = a.register(inst.install_id, b)
            if pl: srv.accept(pl); setup += len(pl) + 8 + len(v6.u(len(a.records)))
            if any(shape(e) not in c.ids for e in b):
                miss += len(b); t['v7_seq'] += gz; t['v7_full_uuid'] += gz; sb += gz; continue
            for key, full in (('v7_seq', False), ('v7_full_uuid', True)):
                f = encode(c, a, inst.install_id, b, d32, full)
                o, ev = decode(c, srv, f, d32, authorized_project=c.project, authorized_origin=inst.install_id)
                assert canonical_source(o, ev, full) == canonical_source(inst.install_id, b, full)
                t[key] += len(f)
                if key == 'v7_seq': sb += len(f)
        per.append(sb / se)
    per.sort()
    return dict(events=n, batches=nb, bytes=t, B_event={k: v / n for k, v in t.items()}, fallback_events=miss, alias_setup_bytes=setup,
                ratio_v7_over_v1=t['v7_seq'] / t['v1_gzip1'], per_install_B_event=dict(min=per[0], p50=per[len(per) // 2], max=per[-1], n=len(per)))

def run():
    results = []
    for profile, session_len in (('low', (15, 60)), ('high', (15, 60)), ('high_short_sessions', (2, 6))):
        base = 'high' if profile.startswith('high') else 'low'
        train = rebatch(corpus(base, 11, 20, 300, session_len), 100)
        c = Catalog.train(PROJECT, train)
        d32 = z.train_dictionary(32768, samples(c, train), level=1)
        cold = len(c.data) + 32768
        for split, seed in (('validation', 22), ('test', 33)):
            for cap in (1, 10, 100, 500):
                ds = rebatch(corpus(base, seed, 6, 300, session_len), cap)
                r = measure(c, d32, ds)
                r.update(profile=profile, split=split, seed=seed, batch_cap=cap, train_seed=11, catalog_bytes=len(c.data), dict_bytes=32768,
                         cold_setup_bytes_per_install=cold + r['alias_setup_bytes'] / 6,
                         breakeven_events_vs_v1=(cold + r['alias_setup_bytes'] / 6) / max(1e-9, (r['B_event']['v1_gzip1'] - r['B_event']['v7_seq'])))
                results.append(r); print(profile, split, cap, {k: round(v, 2) for k, v in r['B_event'].items()}, 'ratio', round(r['ratio_v7_over_v1'], 3), 'fb', r['fallback_events'], flush=True)
    out = HERE.parent / 'results' / 'synth-bench.json'
    out.write_text(json.dumps(dict(config='dict32 level1 train seed 11 only; sequence identity', rows=results), indent=1))

if __name__ == '__main__': run()
