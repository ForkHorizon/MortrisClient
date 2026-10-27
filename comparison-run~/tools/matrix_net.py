#!/usr/bin/env python3
"""Network matrix on an emulator: a 10 000-event backlog (the player was offline) is drained over 2G / 3G / 4G / 5G-like links with the loss rates of the plan
(10 / 4 / 2 / 1 %), for packet sizes 100 / 200 / 500 and the adaptive mode. The link is made by tools/collector2.py (delay, jitter, bandwidth, request drops).
Also: wifi flapping (Wi-Fi + data off 20 s / on 20 s while events are tracked) and one long offline (30 min). Usage: matrix_net.py SERIAL PORT STACK SETNAME [groups: drain,flap,long]"""
import subprocess, sys, time
from pathlib import Path
CR = Path(__file__).resolve().parent.parent
serial, port, stack, setname = sys.argv[1:5]; groups = (sys.argv[5] if len(sys.argv) > 5 else 'drain,flap,long').split(',')
OUT = CR / 'results' / setname
NETS = {'2g': '--delay-ms 600 --jitter-ms 300 --bw-kbps 40 --drop 0.10', '3g': '--delay-ms 150 --jitter-ms 80 --bw-kbps 1000 --drop 0.04',
        '4g': '--delay-ms 50 --jitter-ms 30 --bw-kbps 10000 --drop 0.02', '5g': '--delay-ms 20 --jitter-ms 10 --bw-kbps 50000 --drop 0.01'}
def cell(label, sdk, kv, net='', extra=(), scen_max=1500, tail=2400, quiet=300, data='puzzle_hold_100k.jsonl'):
    if (OUT / label / 'run.json').exists(): return
    cmd = [sys.executable, str(CR / 'tools/run_cell.py'), '--serial', serial, '--port', port, '--label', label, '--sdk', sdk, '--out', str(OUT), '--data', data, '--stack', stack, '--no-install',
           '--scen-max', str(scen_max), '--tail-max', str(tail), '--quiet', str(quiet), '--dump', '--kv'] + kv + list(extra) + ([f'--net-opts={net}'] if net else [])
    try: r = subprocess.run(cmd, capture_output=True, text=True, timeout=scen_max + tail + 900)
    except subprocess.TimeoutExpired: print(time.strftime('%H:%M:%S'), label, 'CELL TIMEOUT', flush=True); return
    print(time.strftime('%H:%M:%S'), label, (r.stdout + r.stderr).strip().splitlines()[-1:], flush=True)
if 'drain' in groups:
    for net, opts in NETS.items():
        for packet, adaptive in ((100, 0), (200, 0), (500, 0), (500, 1)):
            cell(f'drain_{net}_p{packet}_a{adaptive}', 'mortris_v8', ['scenario=burst', 'k=500', 'n=20', 'gap=0.1', f'packet={packet}', f'backlog_packet={packet}', f'adaptive={adaptive}', 'queue_mb=128', 'marker=1'], net=opts, extra=['--offline'], scen_max=600)
        cell(f'drain_{net}_v1', 'mortris_v1', ['scenario=burst', 'k=500', 'n=20', 'gap=0.1', 'queue_mb=128', 'marker=1'], net=opts, extra=['--offline'], scen_max=600)
if 'flap' in groups:
    for sdk in ('mortris_v8', 'mortris_v1'):
        cell(f'flap_{sdk}', sdk, ['scenario=rate', 'hz=5', 'n=1500', 'marker=1', 'profile=realtime'], extra=['--wifi-cycle', '20,20,8'], scen_max=700, quiet=200, tail=900, data='puzzle_slice_14.jsonl')
if 'long' in groups:
    for sdk in ('mortris_v8', 'mortris_v1'):
        cell(f'offline30_{sdk}', sdk, ['scenario=rate', 'hz=10', 'n=18000', 'marker=1'], extra=['--offline'], scen_max=2400, quiet=400, tail=1800)
print('NET_MATRIX_DONE', flush=True)
