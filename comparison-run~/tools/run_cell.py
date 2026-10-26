#!/usr/bin/env python3
"""One measured cell: fresh app data, wire meter, device-side all-process CPU samples, probe run, tail until delivery settles, artifacts pulled.
Usage: run_cell.py --serial S --label L --sdk SDK --out RESULTSDIR [--data FILE] [--net wifi|reverse] [--stack STACKLABEL] [--port 18090] [--kv k=v ...]
Artifacts in OUT/L/: result.json (probe), wire.jsonl (collector2), samples.json (all-process CPU at window start/end/tail end), run.json (driver view), logcat.txt"""
import argparse, json, os, re, subprocess, sys, threading, time
from pathlib import Path
CR = Path(__file__).resolve().parent.parent; ADB = os.path.expanduser('~/Library/Android/sdk/platform-tools/adb'); PKG = 'com.daliys.cmpprobe'
ap = argparse.ArgumentParser(); ap.add_argument('--serial', required=True); ap.add_argument('--label', required=True); ap.add_argument('--sdk', required=True); ap.add_argument('--out', required=True)
ap.add_argument('--data', default='puzzle_slice_00.jsonl'); ap.add_argument('--net', default='reverse'); ap.add_argument('--stack', default=''); ap.add_argument('--port', type=int, default=18090)
ap.add_argument('--apk', default=str(CR / 'work/cmp-arm64.apk')); ap.add_argument('--kv', nargs='*', default=[]); ap.add_argument('--laptop', default=os.environ.get('LAPTOP_IP', '192.168.0.17'))
ap.add_argument('--tail-max', type=int, default=600); ap.add_argument('--quiet', type=int, default=0); ap.add_argument('--expect', type=int, default=0, help='events the backend should end up with (0: only quiet rule)'); ap.add_argument('--scen-max', type=int, default=900); ap.add_argument('--offline', action='store_true'); ap.add_argument('--kill-after', type=float, default=0); ap.add_argument('--net-opts', default=''); ap.add_argument('--project', default='puzzle_gravity_test'); ap.add_argument('--fixed-tail', type=int, default=0); ap.add_argument('--no-install', action='store_true'); ap.add_argument('--dump', action='store_true')
a = ap.parse_args()
OUT = Path(a.out) / a.label; OUT.mkdir(parents=True, exist_ok=True)
def sh(*c, timeout=120):
    try: return subprocess.run((ADB, '-s', a.serial) + c, capture_output=True, text=True, timeout=timeout).stdout
    except subprocess.TimeoutExpired: return ''
SAMPLE = r'''awk '{ if (($14+$15) > 0) print $1, $2, $14+$15 }' /proc/[0-9]*/stat 2>/dev/null; echo CPU $(head -1 /proc/stat); for p in $(pidof com.google.android.gms) $(pidof com.google.android.gms.persistent) $(pidof com.google.android.gms.unstable); do echo PSS $p $(grep ^Pss: /proc/$p/smaps_rollup 2>/dev/null); done; echo FREQ $(cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq 2>/dev/null); echo UP $(cut -d" " -f1 /proc/uptime); echo NETDEV $(grep -E "wlan0|rmnet" /proc/net/dev | tr -s " " | tr "\n" "|"); dumpsys battery | grep -E "temperature|level" | tr "\n" " "; echo'''
def sample(): return sh('shell', SAMPLE, timeout=30)
host = f'{a.laptop}:{a.port}' if a.net == 'wifi' else f'127.0.0.1:{a.port}'
mort = a.sdk.startswith('mortris_')
quiet = a.quiet or {'amplitude': 80, 'amplitude_kotlin': 80, 'ga': 60, 'hyperkit_core': 45, 'hyperkit_ctx': 45, 'mixpanel': 110, 'mortris_v8': 150, 'mortris_v7': 150, 'mortris_v1': 150}.get(a.sdk, 60)
fixed_tail = a.fixed_tail or {'firebase': 150, 'facebook': 90, 'adjust': 60}.get(a.sdk)
# --- meter
if a.net == 'reverse': sh('reverse', f'tcp:{a.port}', f'tcp:{a.port}')
cmd = [sys.executable, str(CR / 'tools/collector2.py'), str(a.port), str(OUT / 'wire.jsonl')]
stack = {}
if mort:
    stack = dict(l.strip().split('=', 1) for l in open(CR / f'work/stacks/{a.stack}.env') if '=' in l); cmd += ['--upstream', f"127.0.0.1:{stack['HTTPPORT']}"]
if a.dump: cmd += ['--dump', str(OUT / 'dump')]
import shlex
cmd += shlex.split(a.net_opts)
subprocess.run(f'lsof -ti tcp:{a.port} | xargs kill 2>/dev/null', shell=True); time.sleep(0.5)
def start_col(): return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=open(OUT / 'collector.err', 'w'))
col = None
if not a.offline: col = start_col(); time.sleep(1.2)
def stats():
    try:
        import urllib.request
        return json.load(urllib.request.urlopen(f'http://127.0.0.1:{a.port}/__stats', timeout=3))
    except Exception: return {}
def dbcount():
    if not mort: return None
    try: return int(subprocess.run(['psql', '-h', '127.0.0.1', '-p', stack['PGPORT'], '-U', 'postgres', '-d', 'mortris_cmp', '-tA', '-c', "SELECT COUNT(*) FROM events WHERE project_id='" + a.project + "'"], capture_output=True, text=True, timeout=20).stdout.strip())
    except Exception: return None
db0 = dbcount()
# --- device
if not a.no_install: sh('install', '-r', a.apk, timeout=300)
sh('shell', 'am', 'force-stop', PKG); sh('shell', 'pm', 'clear', PKG); sh('shell', 'pm', 'grant', PKG, 'android.permission.POST_NOTIFICATIONS')
D = f'/sdcard/Android/data/{PKG}/files'; sh('shell', 'mkdir', '-p', D)
cfg = {'project': a.project, 'sdk': a.sdk, 'host': host, 'server': f'http://{host}', 'data': 'replay.jsonl'}
for kv in a.kv: k, v = kv.split('=', 1); cfg[k] = v
cfg.setdefault('tail_max_s', str(a.tail_max))
cfgfile = OUT / 'config.txt'; cfgfile.write_text('\n'.join(f'{k}={v}' for k, v in cfg.items()) + '\n')
sh('push', str(cfgfile), f'{D}/config.txt'); sh('push', str(CR / 'data' / a.data), f'{D}/replay.jsonl', timeout=600)
sh('logcat', '-c')
# logcat reader thread: reacts to probe markers
events = {}; lines = []; LC = []
def reader():
    # logcat readers die when somebody kills adb logcat processes or the adb server restarts: keep re-attaching (a restarted reader replays the buffer, so markers are not lost)
    seen = set()
    while not events.get('closing'):
        p = subprocess.Popen([ADB, '-s', a.serial, 'logcat', '-v', 'epoch', '-s', 'Unity:I', 'Unity:W', 'Unity:E', 'CMP:E', 'AndroidRuntime:E'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors='replace'); LC.append(p)
        for l in p.stdout:
            key = l[:40] + l[-60:]
            if key in seen and 'CMP ' in l: continue
            seen.add(key); lines.append(l)
            if 'CMP window_start' in l and 'ws' not in events: events['ws'] = time.time(); events['s0'] = sample()
            elif 'CMP window_end' in l and 'we' not in events: events['we'] = time.time(); events['s1'] = sample()
            elif 'CMP scenario_done' in l and 'sd' not in events: events['sd'] = time.time()
            elif 'CMP done' in l: events['done'] = time.time()
            elif 'FATAL EXCEPTION' in l and 'fatal' not in events: events['fatal'] = l
        time.sleep(1)
def poller():
    # second, independent signal: marker names the probe appends to state.txt in its files dir
    seen_n = 0
    while not events.get('closing'):
        txt = sh('shell', f'cat {D}/state.txt 2>/dev/null', timeout=15); marks = txt.split()
        for m in marks[seen_n:]:
            if m == 'window_start' and 'ws' not in events: events['ws'] = time.time(); events['s0'] = sample()
            elif m == 'window_end' and 'we' not in events: events['we'] = time.time(); events['s1'] = sample()
            elif m == 'scenario_done' and 'sd' not in events: events['sd'] = time.time()
            elif m == 'done' and 'done' not in events: events['done'] = time.time()
        seen_n = len(marks)
        if not marks: seen_n = 0
        time.sleep(2)
t = threading.Thread(target=reader, daemon=True); t.start(); threading.Thread(target=poller, daemon=True).start()
bat0 = sh('shell', 'dumpsys battery | grep -E "temperature|level"').replace('\n', ' ')
t_start = time.time(); sh('shell', 'am', 'start', '-n', f'{PKG}/com.unity3d.player.UnityPlayerGameActivity')
def watchdog():
    for attempt in range(2):
        t0 = time.time()
        while 'ws' not in events and 'fatal' not in events and time.time() - t0 < (500 if any('burst' in kv for kv in a.kv) else 150): time.sleep(1)
        if 'ws' in events or 'fatal' in events or a.offline and False: return
        info['watchdog_restarts'] = attempt + 1; sh('shell', 'am', 'force-stop', PKG); sh('shell', 'input', 'keyevent', 'KEYCODE_WAKEUP'); events.clear(); sh('shell', 'am', 'start', '-n', f'{PKG}/com.unity3d.player.UnityPlayerGameActivity')

info = dict(label=a.label, sdk=a.sdk, host=host, net=a.net, data=a.data, kv=a.kv, battery_start=bat0, db0=db0)
watchdog()
# wait for scenario to finish
if a.kill_after:
    while 'ws' not in events and time.time() - t_start < 120: time.sleep(0.5)
    time.sleep(a.kill_after); sh('shell', 'am', 'force-stop', PKG); info['killed_at_s'] = time.time() - events.get('ws', time.time())
    sh('pull', f'{D}/progress.txt', str(OUT / 'progress.txt')); time.sleep(3)
    cfg2 = dict(cfg); cfg2.update({'n': '0', 'scenario': 'rate', 'flush_at_end': '1', 'settle_s': '2'}); (OUT / 'config2.txt').write_text('\n'.join(f'{k}={v}' for k, v in cfg2.items()) + '\n')
    sh('push', str(OUT / 'config2.txt'), f'{D}/config.txt'); events.clear(); sh('shell', 'am', 'start', '-n', f'{PKG}/com.unity3d.player.UnityPlayerGameActivity')
while 'sd' not in events and 'fatal' not in events and time.time() - t_start < (3000 if a.offline else a.scen_max): time.sleep(1)
if a.offline:
    col = start_col(); time.sleep(1.2); info['backend_back_at'] = time.time() - t_start
tail_start = time.time(); last_n = -1; last_change = time.time(); settled = 'timeout'
while 'fatal' not in events and 'sd' in events:
    el = time.time() - tail_start
    if el > a.tail_max: settled = 'tail_max'; break
    if fixed_tail:
        if el >= fixed_tail: settled = 'fixed'; break
    else:
        st = stats(); n = dbcount() if mort else st.get('events', 0)
        if mort and a.expect and n is not None and n - (db0 or 0) >= a.expect: settled = 'all_delivered'; break
        if n != last_n: last_n = n; last_change = time.time()
        # activity on the wire also counts (retries, hello), but only delivery growth resets the quiet timer
        if time.time() - last_change >= quiet and el > 20: settled = 'quiet'; break
    time.sleep(3)
events['s2'] = sample(); info['tail_s'] = time.time() - tail_start; info['settled'] = settled
sh('shell', f'echo 1 > {D}/stop.txt')
for _ in range(60):
    if 'done' in events or 'fatal' in events: break
    time.sleep(1)
time.sleep(1)
sh('pull', f'{D}/result.json', str(OUT / 'result.json'))
info['bat_end'] = sh('shell', 'dumpsys battery | grep -E "temperature|level"').replace('\n', ' ')
info['final_stats'] = stats(); info['db1'] = dbcount(); info['fatal'] = events.get('fatal'); info['wall_s'] = time.time() - t_start
if 'ws' in events and 'we' in events: info['window_wall_s'] = events['we'] - events['ws']
(OUT / 'samples.json').write_text(json.dumps({k: events[k] for k in ('s0', 's1', 's2') if k in events}))
(OUT / 'run.json').write_text(json.dumps(info, indent=1)); (OUT / 'logcat.txt').write_text(''.join(lines))
sh('shell', 'am', 'force-stop', PKG)
if col: col.terminate(); col.wait()
events['closing'] = True
for p in LC: p.kill()
if mort: pass
print(a.label, 'ok' if (OUT / 'result.json').stat().st_size > 10 else 'NO RESULT', info['settled'], round(info['wall_s']), flush=True)
