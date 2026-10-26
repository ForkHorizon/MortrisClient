#!/usr/bin/env python3
"""Table for a delivery/fidelity set (results/fid, results/chaos, results/param): one row per cell. Usage: analyze_fid.py SETNAME [markdown|json]"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); import wire
R = Path(__file__).resolve().parent.parent / 'results' / sys.argv[1]; rows = []
for d in sorted(R.iterdir()):
    if not d.is_dir() or d.name.startswith('warm'): continue
    fid = d / 'fidelity.json'; run = d / 'run.json'
    row = dict(cell=d.name)
    if fid.exists():
        try: row['fid'] = json.loads(fid.read_text())
        except Exception: pass
    if run.exists():
        r = json.loads(run.read_text()); row.update(settled=r.get('settled'), tail_s=round(r.get('tail_s', 0)), wd=r.get('watchdog_restarts'))
        st = r.get('final_stats', {}); row['wire_events'] = st.get('events')
        if r.get('db0') is not None and r.get('db1') is not None: row['db_delta'] = r['db1'] - r['db0']
    wp = d / 'wire.jsonl'
    if wp.exists() and wp.stat().st_size:
        sdk = d.name.split('_', 1)[1] if '_' in d.name else d.name
        for k in ('mortris_v8', 'mortris_v7', 'mortris_v1', 'amplitude_kotlin', 'amplitude', 'ga', 'hyperkit_ctx', 'hyperkit_core', 'mixpanel'):
            if k in d.name: sdk = k; break
        fid_n = row.get('fid', {}).get('delivered_unique') if isinstance(row.get('fid'), dict) else None
        n = fid_n or row.get('db_delta') or row.get('wire_events') or 1
        try: row['wire'] = wire.summarize(str(wp), sdk, n)
        except Exception as e: row['wire_err'] = str(e)
    rows.append(row)
if len(sys.argv) > 2 and sys.argv[2] == 'json': print(json.dumps(rows, indent=1)); sys.exit()
print(f"{'cell':34} {'deliv%':>7} {'full%':>7} {'lost%':>6} {'dup':>4} {'trunc':>5} {'typeΔ':>5} {'B/ev up':>8} {'B/ev +tls':>9} {'req':>5} {'conn':>4} {'settle':>8} {'tail_s':>6}")
for r in rows:
    f = r.get('fid') if isinstance(r.get('fid'), dict) else {}; w = r.get('wire', {})
    print(f"{r['cell']:34} {f.get('delivered_pct', float('nan')):7.1f} {f.get('events_fully_preserved_pct_of_sent', float('nan')):7.1f} {f.get('props_lost_pct', float('nan')):6.2f} {f.get('duplicates', 0):4} {f.get('strings_truncated', 0):5} {f.get('type_changed', 0):5} "
          f"{w.get('per_event_up', float('nan')):8.1f} {w.get('per_event_with_tls', float('nan')):9.1f} {w.get('requests', 0):5} {w.get('connections', 0):4} {str(r.get('settled')):>8} {r.get('tail_s', 0):6}")
