"""Unity IL2CPP probe results -> results/unity_summary.json. CPU is process ticks (10 ms) over replay+drain; baseline = mode none run with the same event stream; calibration = guest wall-time spin."""
import json, os, re, statistics
from collections import defaultdict
from pathlib import Path
R = Path(__file__).resolve().parent / 'results'; cells = defaultdict(list)
def kv(s): return {k: v for k, v in re.findall(r'(\w+)=([^\s]+)', s)}
for d in sorted((R / os.environ.get('UDIR', 'unity')).glob('*_r*')):
    f = d / 'perf.txt'
    if not f.exists(): continue
    t = f.read_text(); m = re.search(r'V7PERF result (.*)', t)
    if not m: continue
    p = kv(m.group(1)); mode, kind = d.name.split('_')[0], d.name.split('_')[1]
    calibs = [float(x) for x in p.get('calibs', '').split(',') if x] + [float(p['calib_start'])]
    row = {k: float(v) for k, v in p.items() if re.fullmatch(r'-?[\d.]+', v)}; row['calib_mean'] = statistics.mean(calibs); row['calibs'] = calibs
    dbm = re.search(r'db_events=(\d+) packets_v2=(\d+) batches_v1=(\d+)', t)
    row.update(db_events=int(dbm.group(1)), packets_v2=int(dbm.group(2)), batches_v1=int(dbm.group(3))) if dbm else None
    row['load'] = float(re.search(r'host_load_start=([\d.]+)', t).group(1)); cells[(kind, mode)].append(row)
allc = sorted(c for rs in cells.values() for r in rs for c in r['calibs']); ref = allc[len(allc) // 20] if allc else 1.0
out = {'reference_calib_ns': ref, 'cells': {}}
for (kind, mode), rs in sorted(cells.items()):
    n = rs[0]['events']; corr = lambda r: ref / r['calib_mean']
    out['cells'][f'{kind}/{mode}'] = {'runs': len(rs), 'events': n,
        'cpu_ms_total_raw': statistics.median(r['cpu_ticks_total'] * 10 for r in rs), 'cpu_ms_total_corrected': statistics.median(r['cpu_ticks_total'] * 10 * corr(r) for r in rs),
        'cpu_ms_replay_corrected': statistics.median(r['cpu_ticks_replay'] * 10 * corr(r) for r in rs), 'cpu_ms_drain_corrected': statistics.median(r['cpu_ticks_drain'] * 10 * corr(r) for r in rs),
        'cpu_spread_pct': 100 * (max(r['cpu_ticks_total'] * corr(r) for r in rs) - min(r['cpu_ticks_total'] * corr(r) for r in rs)) / max(1, statistics.median(r['cpu_ticks_total'] * corr(r) for r in rs)),
        'track_us_p50': statistics.median(r['track_us_p50'] for r in rs), 'track_us_p95': statistics.median(r['track_us_p95'] for r in rs), 'track_us_p99': statistics.median(r['track_us_p99'] for r in rs), 'track_us_max': statistics.median(r['track_us_max'] for r in rs),
        'frame_ms_p99': statistics.median(r['frame_ms_p99'] for r in rs), 'frame_ms_max': statistics.median(r['frame_ms_max'] for r in rs),
        'gc_collections': statistics.median(r['gc0'] for r in rs), 'mono_growth_kb': statistics.median(r['mono_end_replay_kb'] - r['mono_start_kb'] for r in rs), 'mono_peak_kb': statistics.median(r['mono_peak_kb'] for r in rs),
        'pss_growth_mb': statistics.median((r['pss_peak_kb'] - r['pss_start_kb']) / 1024 for r in rs), 'pss_peak_mb': statistics.median(r['pss_peak_kb'] / 1024 for r in rs),
        'db_events': statistics.median(r.get('db_events', 0) for r in rs), 'packets_v2': statistics.median(r.get('packets_v2', 0) for r in rs), 'batches_v1': statistics.median(r.get('batches_v1', 0) for r in rs),
        'drain_ms': statistics.median(r['drain_ms'] for r in rs), 'host_load': [min(r['load'] for r in rs), max(r['load'] for r in rs)]}
# net of the 'none' baseline: the empty player burns CPU per millisecond (render loop), so scale it to each run's own replay/drain duration
raw = {k: v for k, v in cells.items()}
for kind in ('burst', 'paced'):
    base = raw.get((kind, 'none'))
    if not base: continue
    rate_rep = statistics.median(r['cpu_ticks_replay'] * 10 / r['replay_ms'] for r in base); rate_drain = statistics.median(r['cpu_ticks_drain'] * 10 / max(r['drain_ms'], 1) for r in base)
    for mode in ('v1', 'v7'):
        rs = raw.get((kind, mode)); c = out['cells'].get(f'{kind}/{mode}')
        if not rs or not c: continue
        corr = lambda r: ref / r['calib_mean']
        net_rep = [(r['cpu_ticks_replay'] * 10 - rate_rep * r['replay_ms']) * corr(r) for r in rs]; net_dr = [(r['cpu_ticks_drain'] * 10 - rate_drain * r['drain_ms']) * corr(r) for r in rs]
        n = c['events']
        c['net_cpu_us_per_event_replay'] = statistics.median(net_rep) * 1000 / n; c['net_cpu_us_per_event_drain'] = statistics.median(net_dr) * 1000 / n
        c['net_cpu_us_per_event_total'] = statistics.median(a + b for a, b in zip(net_rep, net_dr)) * 1000 / n
        c['net_cpu_spread_pct'] = 100 * (max(a + b for a, b in zip(net_rep, net_dr)) - min(a + b for a, b in zip(net_rep, net_dr))) / max(1, abs(statistics.median(a + b for a, b in zip(net_rep, net_dr))))
        c['baseline_rate_replay_ms_per_s'] = rate_rep * 1000; c['net_pss_mb'] = c['pss_growth_mb'] - out['cells'][f'{kind}/none']['pss_growth_mb']
(R / (os.environ.get('UDIR', 'unity') + '_summary.json')).write_text(json.dumps(out, indent=1))
for k, v in out['cells'].items():
    print(f"{k:12} runs={v['runs']} net_cpu/ev total={v.get('net_cpu_us_per_event_total', float('nan')):7.1f}us (replay {v.get('net_cpu_us_per_event_replay', float('nan')):6.1f} drain {v.get('net_cpu_us_per_event_drain', float('nan')):6.1f}) spread={v.get('net_cpu_spread_pct', float('nan')):5.1f}% track p50/p99={v['track_us_p50']:.1f}/{v['track_us_p99']:.0f}us frame p99={v['frame_ms_p99']:.1f}ms gc={v['gc_collections']:.0f} mono+={v['mono_growth_kb']:.0f}KB pss+={v['pss_growth_mb']:.1f}MB db={v['db_events']:.0f} v2={v['packets_v2']:.0f} v1={v['batches_v1']:.0f}")
