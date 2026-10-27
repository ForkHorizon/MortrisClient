#!/usr/bin/env python3
"""Deep stage profile of the SDK (NOT run yet; for the big run). Needs the profiling APK: PROFILE=1 ./build.sh cmp-prof-arm64.apk (stage timers compiled in) and, for the
allocation sets, PROFILE=1 DEV=1 ./build.sh cmp-prof-dev-arm64.apk (Development player: Unity's GC counters are valid there, CPU numbers are not).
Usage: matrix_profile.py SERIAL SETNAME STACK [groups] [reps]     groups (default all): init rate profile batch burst backlog tls dev
Every cell is a fresh install with the same real events (slice r of data/puzzle_slice_NN.jsonl, so reps differ by player). Results: results/SETNAME/<label>/result.json (+ prof_* keys),
analysis: tools/analyze_profile.py SETNAME."""
import os, subprocess, sys, time
from pathlib import Path
CR = Path(__file__).resolve().parent.parent
serial, setname, stack = sys.argv[1:4]; groups = (sys.argv[4] if len(sys.argv) > 4 else 'init,rate,profile,batch,burst,backlog,tls,dev').split(','); reps = int(sys.argv[5]) if len(sys.argv) > 5 else 3
OUT = CR / 'results' / setname; APK = str(CR / 'work/cmp-prof-arm64.apk'); DEVAPK = str(CR / 'work/cmp-prof-dev-arm64.apk')
installed = {}
def cell(label, sdk, kv, rep, apk=APK, data='puzzle_slice_{rep:02d}.jsonl', quiet=150, tail=900, extra=(), scen_max=1800):
    if (OUT / label / 'run.json').exists(): return
    if installed.get('apk') != apk:
        subprocess.run([str(Path.home() / 'Library/Android/sdk/platform-tools/adb'), '-s', serial, 'install', '-r', apk], capture_output=True); installed['apk'] = apk
    cmd = [sys.executable, str(CR / 'tools/run_cell.py'), '--serial', serial, '--port', os.environ.get('PORT', '18090'), '--label', label, '--sdk', sdk, '--out', str(OUT), '--data', data.format(rep=rep), '--stack', stack, '--no-install',
           '--tail-max', str(tail), '--quiet', str(quiet), '--scen-max', str(scen_max), '--kv'] + kv + list(extra)
    try: r = subprocess.run(cmd, capture_output=True, text=True, timeout=scen_max + tail + 600)
    except subprocess.TimeoutExpired: print(time.strftime('%H:%M:%S'), label, 'CELL TIMEOUT', flush=True); return
    print(time.strftime('%H:%M:%S'), label, (r.stdout + r.stderr).strip().splitlines()[-1:], flush=True)
SDKS = ['mortris_v8', 'mortris_v7', 'mortris_v1']
for rep in range(reps):
    if 'init' in groups:                         # start-up cost and first-use costs: cold start, nothing tracked, 90 s of tail (timers, heartbeat, first flush)
        for sdk in SDKS + ['none', 'noop']:
            cell(f'init_{sdk}_r{rep}', sdk, ['scenario=rate', 'hz=1', 'n=0', 'flush_at_end=1', 'settle_s=4'], rep, quiet=45, tail=90)
    if 'rate' in groups:                         # the question "is one event a second too expensive?": stage costs per event at 0.2 .. 60 events a second, default SDK timers
        for name, kv in (('hz0.2', ['scenario=rate', 'hz=0.2', 'n=60']), ('hz1', ['scenario=rate', 'hz=1', 'n=300']), ('hz5', ['scenario=rate', 'hz=5', 'n=1500']), ('hz30', ['scenario=rate', 'hz=30', 'n=3000']),
                         ('frame1', ['scenario=perframe', 'perframe=1', 'n=3600']), ('frame20', ['scenario=perframe', 'perframe=20', 'n=3000'])):
            for sdk in SDKS: cell(f'rate_{name}_{sdk}_r{rep}', sdk, kv, rep)
    if 'profile' in groups:                      # traffic and wakeups per hour for the three presets (10 minutes each, extrapolated by the analysis)
        for prof in ('realtime', 'standard', 'saver'):
            for name, kv in (('hz1', ['scenario=rate', 'hz=1', 'n=600']), ('hz5', ['scenario=rate', 'hz=5', 'n=3000'])):
                cell(f'profile_{prof}_{name}_r{rep}', 'mortris_v8', kv + [f'profile={prof}'], rep, quiet=400, tail=1200)
    if 'batch' in groups:                        # TrackBatchAsync: frame cost of the call and time until everything is on disk
        for k in (100, 500, 5000, 20000):
            cell(f'batch_k{k}_r{rep}', 'mortris_v8', ['scenario=batch', f'k={k}', 'n=1', 'flush_at_end=1'], rep, data='puzzle_hold_100k.jsonl', quiet=200, tail=1500)
    if 'burst' in groups:                        # Track() in one frame: the buffer-full path (writes the buffer itself)
        for k in (500, 1500, 5000, 20000):
            cell(f'burst_k{k}_r{rep}', 'mortris_v8', ['scenario=burst', f'k={k}', 'n=1', 'flush_at_end=1'], rep, data='puzzle_hold_100k.jsonl', quiet=200, tail=1500)
    if 'backlog' in groups:                      # a player offline, then online: draining 2k / 10k / 50k events; packet size and pause variants
        for events in (2000, 10000, 50000):
            for packet, adaptive, pause in ((200, 0, 0), (500, 0, 0), (500, 1, 300)):
                cell(f'backlog_e{events}_p{packet}_a{adaptive}_w{pause}_r{rep}', 'mortris_v8',
                     ['scenario=batch', 'k=500', f'n={events // 500}', 'gap=0.1', f'backlog_packet={packet}', f'adaptive={adaptive}', f'backlog_pause_ms={pause}', 'queue_mb=256'], rep,
                     data='puzzle_hold_100k.jsonl', quiet=300, tail=2400, extra=['--offline'], scen_max=900)
    if 'tls' in groups:                          # raw TLS bytes per connection, resumption, connections per upload (HTTPS through tools/tlsmeter.py; profiling APK trusts its certificate)
        for name, kv in (('hz1', ['scenario=rate', 'hz=1', 'n=600']), ('hz5', ['scenario=rate', 'hz=5', 'n=1500'])):
            for prof in ('realtime', 'standard'):
                cell(f'tls_{prof}_{name}_r{rep}', 'mortris_v8', kv + [f'profile={prof}'], rep, quiet=300, tail=900, extra=['--tls'])
    if 'dev' in groups:                          # managed allocation attribution (Unity's GC counters need a Development player; compare allocations, not CPU)
        for name, kv in (('hz1', ['scenario=rate', 'hz=1', 'n=300']), ('hz5', ['scenario=rate', 'hz=5', 'n=1500']), ('frame20', ['scenario=perframe', 'perframe=20', 'n=3000'])):
            for sdk in ('mortris_v8', 'mortris_v1'): cell(f'dev_{name}_{sdk}_r{rep}', sdk, kv, rep, apk=DEVAPK)
print('PROFILE_MATRIX_DONE', flush=True)
