#!/usr/bin/env python3
"""Parameter sweeps on the emulator (wire/delivery only): batch size, event rate, burst size. Usage: matrix_param.py SERIAL PORT STACK SETNAME [groups]
groups: batch (Mortris threshold=packet 10/30/100/200 at 20 ev/frame), rate (1/10/30/100 ev/s, SDK defaults), burst (1k/6k/20k/100k in one frame)"""
import subprocess, sys, time
from pathlib import Path
CR = Path(__file__).resolve().parent.parent; serial, port, stack, setname = sys.argv[1:5]; groups = (sys.argv[5] if len(sys.argv) > 5 else 'batch,rate,burst').split(',')
OUT = CR / 'results' / setname
def cell(label, sdk, data, kv, n, quiet=100, tail=900, extra=()):
    if (OUT / label / 'run.json').exists(): return
    r = subprocess.run([sys.executable, str(CR / 'tools/run_cell.py'), '--serial', serial, '--port', port, '--label', label, '--sdk', sdk, '--out', str(OUT), '--data', data, '--stack', stack, '--no-install',
                        '--tail-max', str(tail), '--quiet', str(quiet), '--expect', str(n), '--kv'] + kv + list(extra), capture_output=True, text=True)
    print(time.strftime('%H:%M:%S'), label, (r.stdout + r.stderr).strip().splitlines()[-1:], flush=True)
if 'batch' in groups:
    for sdk in ('mortris_v8', 'mortris_v7', 'mortris_v1'):
        for b in (10, 30, 100, 200):
            cell(f'batch{b}_{sdk}', sdk, 'puzzle_slice_12.jsonl', ['scenario=perframe', 'perframe=20', 'n=3000', f'threshold={b}', f'packet={b}', 'flush_at_end=1'], 3000)
if 'rate' in groups:
    for sdk in ('mortris_v8', 'mortris_v1', 'amplitude_kotlin', 'ga'):
        for hz, n in ((1, 300), (10, 1500), (30, 3000), (100, 6000)):
            cell(f'rate{hz}_{sdk}', sdk, 'puzzle_hold_100k.jsonl', ['scenario=rate', f'hz={hz}', f'n={n}'], n)   # no flush_at_end: the SDK's own timers decide
if 'burst' in groups:
    for sdk in ('mortris_v8', 'mortris_v1', 'ga', 'amplitude', 'amplitude_kotlin', 'hyperkit_ctx', 'mixpanel'):
        for k in [int(x) for x in __import__('os').environ.get('BURST_KS', '1000,6000,20000,100000').split(',')]:
            if k == 100000 and sdk not in __import__('os').environ.get('BURST100', sdk).split(','): continue
            cell(f'burst{k}_{sdk}', sdk, 'puzzle_hold_100k.jsonl', ['scenario=burst', f'k={k}', 'n=1', 'flush_at_end=1', 'tail_max_s=1200'], k, quiet=150, tail=int(__import__('os').environ.get('BURST_TAIL', '1200')), extra=['--dump'] if k <= 20000 else [])
print('PARAM_DONE', flush=True)
