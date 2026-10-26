#!/usr/bin/env python3
"""Phone CPU/latency/GC/memory/wire matrix. Resumable: a cell with run.json is skipped. Usage: matrix_cpu.py SERIAL SETNAME REPS [sdk,sdk,...] [data-prefix]
rep r uses slice r of the dataset for EVERY sdk (paired design)."""
import subprocess, sys, os, json, time
from pathlib import Path
CR = Path(__file__).resolve().parent.parent; serial, setname, reps = sys.argv[1], sys.argv[2], int(sys.argv[3])
SDKS = (sys.argv[4] if len(sys.argv) > 4 else 'none,noop,mortris_v1,mortris_v7,mortris_v8,mortris_v8c,amplitude,amplitude_kotlin,ga,firebase,facebook,adjust,hyperkit_core,hyperkit_ctx,mixpanel').split(',')
prefix = sys.argv[5] if len(sys.argv) > 5 else 'puzzle'
SCEN = {'A': ['scenario=rate', 'hz=10', 'n=400'], 'B': ['scenario=perframe', 'perframe=20', 'n=3000']}
OUT = CR / 'results' / setname
def run(label, sdk, scen, rep):
    if (OUT / label / 'run.json').exists(): return
    kv = list(SCEN[scen]) + ['flush_at_end=1']; real = sdk
    if sdk == 'mortris_v8c': real = 'mortris_v8'; kv.append('v8content=1')
    n = 3000 if scen == 'B' else 400
    if sdk == 'adjust': kv = [x for x in kv if not x.startswith('n=')] + ['n=300']; n = 300
    cmd = [sys.executable, str(CR / 'tools/run_cell.py'), '--serial', serial, '--label', label, '--sdk', real, '--out', str(OUT), '--data', f'{prefix}_slice_{rep:02d}.jsonl',
           '--stack', 'cpu', '--tail-max', '150', '--quiet', '20', '--expect', str(n), '--no-install', '--fixed-tail', {'firebase': '60', 'facebook': '40', 'adjust': '30'}.get(sdk, '0'), '--kv'] + kv
    try: r = subprocess.run(cmd, capture_output=True, text=True, timeout=1500)
    except subprocess.TimeoutExpired: print(time.strftime('%H:%M:%S'), label, 'CELL TIMEOUT', flush=True); subprocess.run('pkill -f "run_cell.py --serial '+serial+'"; lsof -ti tcp:18090 | xargs kill', shell=True); return
    print(time.strftime('%H:%M:%S'), (r.stdout + r.stderr).strip().splitlines()[-1:] , flush=True)
for rep in range(reps):
    for scen in ('B', 'A'):
        for sdk in SDKS:
            run(f'{sdk}_{scen}_r{rep}', sdk, scen, rep)
print('MATRIX_DONE', flush=True)
