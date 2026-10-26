#!/usr/bin/env python3
"""Delivery + field preservation on the emulator (not for CPU numbers): datasets x sdks, marker=1, every event carries its index, long drain tails.
Usage: matrix_fid.py SERIAL PORT STACK SETNAME"""
import subprocess, sys, json, time
from pathlib import Path
CR = Path(__file__).resolve().parent.parent; serial, port, stack, setname = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
OUT = CR / 'results' / setname
DATASETS = [('puzzle', 'puzzle_gravity_test', 'puzzle_slice_10.jsonl', 'puzzle_train_20k.jsonl'), ('casual', 'casual_test', 'casual_slice_00.jsonl', 'casual_train_20k.jsonl'),
            ('midcore', 'midcore_test', 'midcore_slice_00.jsonl', 'midcore_train_20k.jsonl'), ('telemetry', 'telemetry_test', 'telemetry_slice_00.jsonl', 'telemetry_train_20k.jsonl')]
SDKS = ['mortris_v1', 'mortris_v7', 'mortris_v8', 'amplitude', 'amplitude_kotlin', 'ga', 'hyperkit_ctx', 'mixpanel']
def cell(label, sdk, project, data, extra, quiet, n=2000):
    if (OUT / label / 'run.json').exists(): return
    cmd = [sys.executable, str(CR / 'tools/run_cell.py'), '--serial', serial, '--port', port, '--label', label, '--sdk', sdk, '--out', str(OUT), '--data', data, '--stack', stack, '--project', project,
           '--tail-max', '500', '--quiet', str(quiet), '--expect', str(n), '--no-install', '--dump', '--kv', 'scenario=perframe', 'perframe=20', f'n={n}', 'marker=1', 'flush_at_end=1'] + extra
    r = subprocess.run(cmd, capture_output=True, text=True); print(time.strftime('%H:%M:%S'), label, (r.stdout + r.stderr).strip().splitlines()[-1:], flush=True)
for name, project, hold, train in DATASETS:
    for i in (1, 2): cell(f'warm_{name}_v8_{i}', 'mortris_v8', project, train, [], 20, n=3000)   # trains the V8 dictionary for this project (not measured)
    for sdk in SDKS:
        if sdk == 'mortris_v7' and name != 'puzzle': continue
        label = f'{name}_{sdk}'
        cell(label, sdk, project, hold, [], {'ga': 90, 'amplitude': 110, 'amplitude_kotlin': 110, 'mixpanel': 130}.get(sdk, 60))
        d = OUT / label
        if (d / 'run.json').exists() and not (d / 'fidelity.json').exists():
            stk = dict(l.strip().split('=', 1) for l in open(CR / f'work/stacks/{stack}.env') if '=' in l)
            r = subprocess.run([sys.executable, str(CR / 'tools/fidelity.py'), str(d), sdk, str(CR / 'data' / hold), '2000', '--pg', stk['PGPORT'], '--project', project], capture_output=True, text=True)
            (d / 'fidelity.json').write_text(r.stdout or r.stderr)
    for sdk in ('firebase', 'facebook', 'adjust'):
        d = OUT / f'{name}_{sdk}'; d.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([sys.executable, str(CR / 'tools/fidelity.py'), str(d), sdk, str(CR / 'data' / hold), '2000'], capture_output=True, text=True); (d / 'fidelity.json').write_text(r.stdout or r.stderr)
print('FID_DONE', flush=True)
