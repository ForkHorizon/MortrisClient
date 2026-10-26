#!/usr/bin/env python3
"""Aggregates a matrix set: per (sdk, scenario) over reps: mean, sd, 95% CI (Student t), and paired net-of-baseline values. Usage: analyze_cpu.py SETNAME > results/SETNAME/summary.json (+ markdown table on stderr)"""
import json, math, re, statistics, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); import wire
R = Path(__file__).resolve().parent.parent / 'results' / sys.argv[1]
T95 = {1: 12.71, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}
def ci(v):
    v = [x for x in v if x is not None]
    if not v: return None
    m = statistics.mean(v); sd = statistics.stdev(v) if len(v) > 1 else 0.0; h = T95.get(len(v) - 1, 2.0) * sd / math.sqrt(len(v)) if len(v) > 1 else 0.0
    return dict(mean=m, sd=sd, ci95=h, n=len(v), min=min(v), max=max(v))
def parse_sample(txt):
    procs = {}; cpu = None
    for l in txt.splitlines():
        m = re.match(r'^(\d+) \((.*)\) (\d+)$', l)
        if m: procs[int(m.group(1))] = (m.group(2), int(m.group(3)))
        elif l.startswith('CPU '): f = l.split()[2:]; cpu = [int(x) for x in f[:8]]
    return procs, cpu
def cpu_split(samples, app_pid_hint=None):
    if 's0' not in samples or 's2' not in samples: return {}
    p0, c0 = parse_sample(samples['s0']); p2, c2 = parse_sample(samples['s2'])
    out = dict(app=0, gms=0, other=0)
    for pid, (name, t) in p2.items():
        d = t - p0.get(pid, (name, 0))[1]
        if d <= 0: continue
        if 'cmpprobe' in name or name.startswith('ys.cmpprobe') or name == 'com.daliys.cmp': out['app'] += d
        elif 'gms' in name or 'gsf' in name or 'google' in name: out['gms'] += d
        else: out['other'] += d
    if c0 and c2: out['system_busy'] = sum(c2[i] - c0[i] for i in (0, 1, 2, 5, 6)); out['system_total'] = sum(c2) - sum(c0)
    return out
cells = defaultdict(list)
def mort_like(sdk): return sdk.startswith('mortris')
for d in sorted(R.iterdir()):
    if not (d / 'run.json').exists() or not (d / 'result.json').exists(): continue
    m = re.match(r'^(.*)_([A-Z])_r(\d+)$', d.name)
    if not m: continue
    sdk, scen, rep = m.group(1), m.group(2), int(m.group(3))
    try: r = json.load(open(d / 'result.json')); run = json.load(open(d / 'run.json')); samples = json.load(open(d / 'samples.json'))
    except Exception: continue
    ev = r.get('events', 0) or 1; ft = r['frame_dt_ms']; tk = r['track_us']
    row = dict(rep=rep, events=ev, cpu_scen_ms_per_ev=r['cpu_ticks_scenario'] * 10 / ev, cpu_tail_ms=r['cpu_ticks_tail'] * 10, cpu_tail_s=r['tail_s'],
               cpu_total_ms_per_ev=(r['cpu_ticks_scenario'] + r['cpu_ticks_tail']) * 10 / ev, track_p50=tk['p50'], track_p99=tk['p99'], track_max=tk['max'], track_mean=tk['mean'],
               frame_p99=ft['p99'], frame_max=ft['max'], jank33=ft['jank33'], jank50=ft['jank50'], fps=ft['fps_mean'], gc0=r['gc_mono'][0], art_bytes_per_ev=r.get('art_bytes_scenario', 0) / ev, art_gc=r.get('art_gc_count_scenario'),
               pss_peak_mb=r['mem_peak'][0] / 1024, pss_before_mb=r['mem_before'][0] / 1024, java_peak_mb=r['mem_peak'][1] / 1024, native_peak_mb=r['mem_peak'][2] / 1024, init_ms=r.get('init_ms'), init_cpu_ms=r.get('init_cpu_ticks', 0) * 10,
               settled=run.get('settled'), delivered=(run['db1'] - run['db0']) if run.get('db0') is not None and run.get('db1') is not None else run['final_stats'].get('events'), adapter_init=r.get('adapter_init'))
    row.update({'all_' + k: v for k, v in cpu_split(samples).items()})
    row['scen_s'] = r['scenario_ms'] / 1000; row['cpu_scen_ticks'] = r['cpu_ticks_scenario']; row['cpu_tail_ticks'] = r['cpu_ticks_tail']
    def up(t):
        m = re.search(r'^UP ([\d.]+)', t or '', re.M); return float(m.group(1)) if m else None
    def net(t):
        m = re.search(r'^NETDEV (.*)$', t or '', re.M)
        if not m: return None
        rx = tx = 0
        for part in m.group(1).split('|'):
            f = part.split()
            if len(f) >= 10 and f[0].startswith(('wlan0', 'rmnet')): rx += int(f[1]); tx += int(f[9])
        return rx, tx
    if 's0' in samples and 's2' in samples:
        row['win_s'] = (up(samples['s2']) or 0) - (up(samples['s0']) or 0); a0, a2 = net(samples['s0']), net(samples['s2'])
        if a0 and a2: row['wlan_rx'] = a2[0] - a0[0]; row['wlan_tx'] = a2[1] - a0[1]
    st = run['final_stats']; row['wire_events'] = st.get('events') if st.get('events') else None
    row['delivered_n'] = row['delivered'] if mort_like(sdk) else (row['wire_events'] or 0)
    wp = d / 'wire.jsonl'
    if wp.exists() and wp.stat().st_size > 0:
        real = 'mortris_v8' if sdk.startswith('mortris_v8') else sdk
        try: row['wire'] = wire.summarize(str(wp), real, ev)
        except Exception as e: row['wire_err'] = str(e)
    cells[(sdk, scen)].append(row)
summary = {}
# baseline-adjusted (engine) CPU: subtract the `none` cell of the same rep and scenario, per second of scenario / tail / window
for (sdk, scen), rows in cells.items():
    base = {r['rep']: r for r in cells.get(('none', scen), [])}
    for r in rows:
        b = base.get(r['rep'])
        if not b: continue
        rs = b['cpu_scen_ticks'] / b['scen_s']; rt = b['cpu_tail_ticks'] / max(b['cpu_tail_s'], 1)
        r['net_scen_ms'] = (r['cpu_scen_ticks'] - rs * r['scen_s']) * 10; r['net_tail_ms'] = (r['cpu_tail_ticks'] - rt * r['cpu_tail_s']) * 10
        r['net_total_ms_per_ev'] = (r['net_scen_ms'] + r['net_tail_ms']) / r['events']; r['net_scen_ms_per_ev'] = r['net_scen_ms'] / r['events']
        if r.get('win_s') and b.get('win_s'):
            for k in ('all_app', 'all_gms', 'all_other', 'all_system_busy'):
                if r.get(k) is not None and b.get(k) is not None: r['net' + k] = (r[k] - b[k] / b['win_s'] * r['win_s']) * 10 / r['events']
        if r.get('wire') and r.get('delivered_n'):
            w = r['wire']; dn = r['delivered_n']; r['up_per_delivered'] = (w['up_header'] + w['up_body']) / dn; r['up_tls_per_delivered'] = (w['up_header'] + w['up_body'] + w['with_tls'] - w['cleartext_total']) / dn  # tls added both ways, reported on the uplink column for brevity
            r['total_per_delivered'] = w['with_tls'] / dn; r['delivered_share'] = dn / r['events']
        if r.get('wlan_rx') is not None and b.get('wlan_rx') is not None and b.get('win_s'):
            r['wlan_tx_net'] = r['wlan_tx'] - b['wlan_tx'] / b['win_s'] * r['win_s']; r['wlan_rx_net'] = r['wlan_rx'] - b['wlan_rx'] / b['win_s'] * r['win_s']
def agg(rows, key):
    return ci([r.get(key) for r in rows])
KEYS = ['net_total_ms_per_ev', 'net_scen_ms_per_ev', 'net_scen_ms', 'net_tail_ms', 'netall_app', 'netall_gms', 'netall_other', 'netall_system_busy', 'up_per_delivered', 'total_per_delivered', 'delivered_share', 'wlan_tx_net', 'wlan_rx_net', 'cpu_scen_ms_per_ev', 'cpu_total_ms_per_ev', 'cpu_tail_ms', 'track_p50', 'track_p99', 'track_max', 'frame_p99', 'frame_max', 'jank33', 'jank50', 'fps', 'gc0', 'art_bytes_per_ev', 'art_gc', 'pss_peak_mb', 'pss_before_mb', 'java_peak_mb', 'native_peak_mb', 'init_ms', 'init_cpu_ms', 'all_app', 'all_gms', 'all_other', 'all_system_busy']
for (sdk, scen), rows in sorted(cells.items()):
    s = {k: agg(rows, k) for k in KEYS}; s['reps'] = len(rows); s['delivered'] = [r['delivered'] for r in rows]; s['events'] = [r['events'] for r in rows]; s['settled'] = [r['settled'] for r in rows]
    w = [r['wire'] for r in rows if 'wire' in r]
    if w:
        for k in ('per_event_body', 'per_event_up', 'per_event_cleartext', 'per_event_with_tls', 'requests', 'connections'): s['wire_' + k] = ci([x.get(k) for x in w])
    # paired net vs baseline 'none' (same rep)
    base = {r['rep']: r for r in cells.get(('none', scen), [])}
    for key in ('cpu_total_ms_per_ev', 'all_app', 'all_gms', 'all_system_busy', 'art_bytes_per_ev', 'gc0', 'pss_peak_mb'):
        diffs = [r[key] - base[r['rep']][key] for r in rows if r['rep'] in base and r.get(key) is not None and base[r['rep']].get(key) is not None]
        if diffs: s['net_' + key] = ci(diffs)
    summary[f'{sdk}|{scen}'] = s
json.dump(summary, open(R / 'summary.json', 'w'), indent=1)
def f(x, k='mean', p=1): return '-' if not x else f"{x[k]:.{p}f}±{x['ci95']:.{p}f}"
print(f"{'sdk':18} {'scen':4} {'n':2} {'netcpu/ev':>12} {'scen/ev':>12} {'allapp/ev':>11} {'gms/ev':>9} {'track p50':>10} {'p99':>9} {'frame p99':>9} {'jank33':>7} {'PSS MB':>10} {'B/ev up':>9} {'B/ev +tls':>10}", file=sys.stderr)
for k, s in summary.items():
    sdk, scen = k.split('|')
    print(f"{sdk:18} {scen:4} {s['reps']:2} {f(s['net_total_ms_per_ev'],p=3):>12} {f(s['net_scen_ms_per_ev'],p=3):>12} {f(s['netall_app'],p=3):>11} {f(s['netall_gms'],p=3):>9} {f(s['track_p50'],p=0):>10} {f(s['track_p99'],p=0):>9} {f(s['frame_p99'],p=1):>9} {f(s['jank33'],p=1):>7} {f(s['pss_peak_mb'],p=0):>10} {f(s['up_per_delivered'],p=1):>9} {f(s['total_per_delivered'],p=1):>10}", file=sys.stderr)
