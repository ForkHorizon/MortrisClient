#!/usr/bin/env python3
"""Failure scenarios. Usage: matrix_chaos.py SERIAL PORT STACK SETNAME APK_INSTALL(0/1) [scenarios] [sdks]
scenarios: kill (force-stop 20 s into a 50 ev/s run, relaunch, drain), offline (backend down for the whole run, then up), net_bad (400 ms +-200, 128 kbit/s, 8% requests die), net_loss (2% die)
Each cell: marker=1 events, dump of what the backend received, fidelity.json (delivered unique, duplicates, lost properties)."""
import subprocess, sys, time
from pathlib import Path
CR = Path(__file__).resolve().parent.parent; serial, port, stack, setname = sys.argv[1:5]
scen = (sys.argv[6] if len(sys.argv) > 6 else 'kill,net_loss,net_bad,offline').split(','); sdks = (sys.argv[7] if len(sys.argv) > 7 else 'mortris_v8,mortris_v1,amplitude,amplitude_kotlin,ga,hyperkit_ctx,mixpanel').split(',')
OUT = CR / 'results' / setname; apk = str(CR / 'work/cmp2-arm64.apk')
if sys.argv[5] == '1': subprocess.run([str(Path.home() / 'Library/Android/sdk/platform-tools/adb'), '-s', serial, 'install', '-r', apk], capture_output=True)
OFFLINE_N = int(__import__('os').environ.get('OFFLINE_N', '6000')); OFFLINE_HZ = int(__import__('os').environ.get('OFFLINE_HZ', '10'))
def cell(sc, sdk):
    label = f'{sc}_{sdk}'
    if (OUT / label / 'run.json').exists(): return
    DATA = 'puzzle_hold_100k.jsonl' if sc == 'offline' else 'puzzle_slice_11.jsonl'
    base = ['--serial', serial, '--port', port, '--label', label, '--sdk', sdk, '--out', str(OUT), '--data', DATA, '--stack', stack, '--no-install', '--dump', '--tail-max', '1200', '--quiet', '120' if sc != 'offline' else __import__('os').environ.get('OFFLINE_QUIET', '300')]
    n = 3000; kv = ['marker=1', 'flush_at_end=1']
    if sc == 'kill': extra = ['--kill-after', '20']; kv += ['scenario=rate', 'hz=50', 'n=3000', 'progress=1']
    elif sc == 'offline': extra = ['--offline']; n = OFFLINE_N; kv += ['scenario=rate', f'hz={OFFLINE_HZ}', f'n={n}']
    elif sc == 'net_bad': extra = ['--net-opts=--delay-ms 400 --jitter-ms 200 --bw-kbps 128 --drop 0.08']; kv += ['scenario=perframe', 'perframe=20', 'n=3000']
    else: extra = ['--net-opts=--drop 0.02']; kv += ['scenario=perframe', 'perframe=20', 'n=3000']
    r = subprocess.run([sys.executable, str(CR / 'tools/run_cell.py')] + base + extra + ['--expect', str(n), '--kv'] + kv, capture_output=True, text=True)
    print(time.strftime('%H:%M:%S'), label, (r.stdout + r.stderr).strip().splitlines()[-1:], flush=True)
    d = OUT / label
    if (d / 'run.json').exists():
        stk = dict(l.strip().split('=', 1) for l in open(CR / f'work/stacks/{stack}.env') if '=' in l)
        f = subprocess.run([sys.executable, str(CR / 'tools/fidelity.py'), str(d), sdk, str(CR / 'data' / DATA), str(n), '--pg', stk['PGPORT']], capture_output=True, text=True); (d / 'fidelity.json').write_text(f.stdout or f.stderr)
for sc in scen:
    for sdk in sdks: cell(sc, sdk)
print('CHAOS_DONE', flush=True)
