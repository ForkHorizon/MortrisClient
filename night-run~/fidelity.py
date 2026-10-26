"""How much of each real event survives an SDK. Needs runs with marker (zz_n) and DUMP_FULL=1: results/android/<label>/<mode>-r0.col.jsonl.events.jsonl
Usage: fidelity.py LABEL MODE[,MODE..] N   -> results/fidelity_<LABEL>.json"""
import json, sys
from pathlib import Path
R = Path(__file__).resolve().parent; label, modes, n = sys.argv[1], sys.argv[2].split(','), int(sys.argv[3])
orig = [json.loads(l) for _, l in zip(range(n), open(R / 'work/replay_real_20k.jsonl'))]
def props_of(mode, e):
    if mode.startswith('ga'): return e.get('custom_fields') if e.get('category') == 'design' else None, e.get('event_id')
    if mode.startswith('amp'): return e.get('event_properties'), e.get('event_type')
    if mode.startswith('hyperkit'):
        c = e.get('context');
        try: return (json.loads(c) if c else {}), e.get('event')
        except Exception: return {}, e.get('event')
    return None, None
out = {}
for mode in modes:
    f = R / 'results/android' / label / f'{mode}-r0.col.jsonl.events.jsonl'
    if not f.exists(): out[mode] = 'no data'; continue
    got = {}; dup = 0; noid = 0
    for l in open(f):
        e = json.loads(l); p, name = props_of(mode, e)
        if p is None: continue
        k = p.get('zz_n') if mode != 'hyperkit_core' else None
        if k is None: noid += 1; continue
        if k in got: dup += 1
        got[k] = (name, p)
    full = lost_props = total_props = type_changed = str_trunc = value_changed = events_missing_all_props = 0
    lost_kinds = {}
    for i, o in enumerate(orig):
        if i not in got: continue
        name, p = got[i]; op = dict(o['props']); op['zz_n'] = i
        ok = True
        for k, v in op.items():
            total_props += 1
            if k not in p: lost_props += 1; ok = False; lost_kinds[type(v).__name__ + ('_empty' if v == '' else '')] = lost_kinds.get(type(v).__name__ + ('_empty' if v == '' else ''), 0) + 1; continue
            g = p[k]
            if g != v:
                ok = False
                if isinstance(v, str) and isinstance(g, str) and v.startswith(g): str_trunc += 1
                elif type(g) != type(v): type_changed += 1
                else: value_changed += 1
        full += ok
    out[mode] = {'sent': len(orig), 'delivered_unique': len(got), 'delivered_share_pct': 100 * len(got) / len(orig), 'duplicates': dup, 'events_fully_preserved_pct_of_delivered': 100 * full / max(len(got), 1),
                 'properties_total': total_props, 'properties_lost': lost_props, 'properties_lost_pct': 100 * lost_props / max(total_props, 1), 'lost_by_value_kind': lost_kinds, 'strings_truncated': str_trunc,
                 'type_changed': type_changed, 'value_changed': value_changed}
(R / f'results/fidelity_{label}.json').write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))
