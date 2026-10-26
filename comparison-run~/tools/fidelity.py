#!/usr/bin/env python3
"""Field preservation of one cell run with marker=1 (every event carries zz_n=index). Compares what the backend ended up with against the dataset.
Usage: fidelity.py CELLDIR SDK DATASET.jsonl N [--pg PORT]   -> prints JSON. Mortris: reads the events table (the newest install). Competitors: collector2 --dump events.
Firebase/Facebook/Adjust cannot be read from the wire here; rule_based() applies their documented limits to the dataset instead (flagged as predicted)."""
import json, subprocess, sys
from pathlib import Path
cell, sdk, data, N = Path(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4])
orig = [json.loads(l) for _, l in zip(range(N), open(data))]
for i, o in enumerate(orig): o['props']['zz_n'] = i
PROJECT = sys.argv[sys.argv.index('--project') + 1] if '--project' in sys.argv else 'puzzle_gravity_test'
def mortris_rows(pg):
    q = f"select name, properties::text from events where project_id='{PROJECT}' and install_id=(select install_id from events where project_id='{PROJECT}' order by received_at desc limit 1) and name not like 'sys\\_%' and properties ? 'zz_n'"
    out = subprocess.run(['psql', '-h', '127.0.0.1', '-p', str(pg), '-U', 'postgres', '-d', 'mortris_cmp', '-tA', '-F', '\t', '-c', q], capture_output=True, text=True).stdout
    for l in out.splitlines():
        name, p = l.split('\t', 1); yield name, json.loads(p)
def dump_rows():
    f = cell / 'dump' / 'events.jsonl'
    if not f.exists(): return
    for l in open(f):
        e = json.loads(l)
        if sdk.startswith('amplitude'): yield e.get('event_type'), e.get('event_properties') or {}
        elif sdk == 'ga':
            if e.get('category') == 'design': yield e.get('event_id'), e.get('custom_fields') or {}
        elif sdk == 'hyperkit_ctx':
            try: yield e.get('event'), json.loads(e.get('context') or '{}')
            except Exception: pass
        elif sdk == 'mixpanel': yield e.get('event'), e.get('properties') or {}
def rule_based():
    kept = {}
    for i, o in enumerate(orig):
        p = {}
        for k, v in o['props'].items():
            if sdk in ('firebase', 'facebook') and len(p) >= 25: continue
            if len(k) > 40 and sdk in ('firebase', 'facebook'): continue
            if isinstance(v, str) and len(v) > 100 and sdk in ('firebase', 'facebook'): v = v[:100]
            if isinstance(v, bool) and sdk == 'firebase': v = int(v)
            if sdk == 'adjust': v = str(v)
            p[k] = v
        kept[i] = (o['name'], p)
    return kept
rows = None
if sdk.startswith('mortris'): rows = list(mortris_rows(int(sys.argv[sys.argv.index('--pg') + 1])))
elif sdk in ('firebase', 'facebook', 'adjust'): rows = None
else: rows = list(dump_rows())
got = {}; dup = 0
if rows is None: got = rule_based(); basis = 'rule_based_prediction'
else:
    basis = 'wire'
    for name, p in rows:
        k = p.get('zz_n')
        if k is None: continue
        if k in got: dup += 1
        got[int(k)] = (name, p)
def same(v, g):
    if isinstance(v, bool) or isinstance(g, bool): return v is g if isinstance(v, bool) and isinstance(g, bool) else False
    if isinstance(v, (int, float)) and isinstance(g, (int, float)): return abs(v - g) <= 1e-6 * max(1, abs(v))
    return v == g
full = lost = total = trunc = tchg = vchg = 0; kinds = {}
for i, o in enumerate(orig):
    if i not in got: continue
    name, p = got[i]; ok = True
    for k, v in o['props'].items():
        total += 1
        if k not in p:
            lost += 1; ok = False; kk = type(v).__name__ + ('_empty' if v == '' else ''); kinds[kk] = kinds.get(kk, 0) + 1; continue
        g = p[k]
        if not same(v, g):
            ok = False
            if isinstance(v, str) and isinstance(g, str) and v.startswith(g): trunc += 1
            elif type(g) != type(v) and not (isinstance(v, (int, float)) and isinstance(g, (int, float)) and not isinstance(g, bool)): tchg += 1
            else: vchg += 1
    full += ok
print(json.dumps(dict(sdk=sdk, basis=basis, sent=len(orig), delivered_unique=len(got), delivered_pct=100 * len(got) / len(orig), duplicates=dup, events_fully_preserved=full, events_fully_preserved_pct_of_sent=100 * full / len(orig),
                      props_total=total, props_lost=lost, props_lost_pct=100 * lost / max(total, 1), lost_by_kind=kinds, strings_truncated=trunc, type_changed=tchg, value_changed=vchg)))
