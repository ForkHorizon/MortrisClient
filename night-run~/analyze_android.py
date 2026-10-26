"""Aggregates results/android/<label>/<mode>-r<rep>.{logcat.txt,col.jsonl} into results/android_summary.json + a markdown table."""
import json, re, statistics, sys
from collections import defaultdict
from pathlib import Path
R = Path(__file__).resolve().parent / 'results'; cells = defaultdict(list)
LABELS = sys.argv[1].split(',') if len(sys.argv) > 1 else None; OUTNAME = sys.argv[2] if len(sys.argv) > 2 else 'android_summary'
def kv(line): return {k: v for k, v in re.findall(r'(\w+)=([^\s]+)', line)}
for log in sorted((R / 'android').glob('*/*.logcat.txt')):
    label, mode = log.parent.name, log.name.split('-r')[0]
    if label == 'smoke' or (LABELS and label not in LABELS) or (not LABELS and label in ('fid',)): continue
    if label == 'c1' and mode == 'firebase' and LABELS and 'c1b' in LABELS: continue  # c1 ran Firebase in debug mode; c1b is the production-mode rerun
    t = log.read_text(); m = re.search(r'perf2 (.*)', t)
    if not m: continue
    p = kv(m.group(1)); calibs = [float(x.split(':')[1]) for x in p.get('calibs', '').split(',') if ':' in x and float(x.split(':')[1]) > 0.5]
    row = {k: float(v) for k, v in p.items() if k != 'calibs' and re.fullmatch(r'-?[\d.]+', v)}
    allc = [c for c in calibs + [row['calib0'], row['calib_end']] if c > 0.5]; row['calib_samples'] = allc
    row['calib_mean'] = statistics.mean(allc) if allc else 1.0; row['calib_best_run'] = min(allc) if allc else 1.0
    pi = re.search(r'BENCH\s*: perf (init_cpu_ms.*)', t)
    if pi:
        q = kv(pi.group(1)); row['init_cpu_ms'] = float(q['init_cpu_ms']); row['init_alloc_kb'] = float(q['init_alloc']) / 1024
    dk = re.search(r'disk_kb=(.*)', t)
    row['disk_kb'] = sum(int(x.split()[0]) for x in dk.group(1).split(';') if x.strip() and x.split()[0].isdigit() and 'gms' not in x) if dk else -1
    g = re.search(r'gms_cpu_ticks_delta=(\{.*\})', t); row['gms_cpu_ms'] = sum(eval(g.group(1)).values()) * 10 if g else 0
    row['host_load'] = float(re.search(r'host_load_at_start=([\d.]+)', t).group(1))
    col = log.with_name(log.name.replace('.logcat.txt', '.col.jsonl'))
    rows = [json.loads(l) for l in open(col)] if col.exists() else []
    data = [r for r in rows if r['events'] != 0 or '/events' in r['path'] or r['path'].startswith('/amp')]
    row['wire_body'] = sum(r['req_body_bytes'] for r in rows); row['wire_hdr'] = sum(r['req_header_bytes'] + r['resp_bytes'] for r in rows)
    row['delivered'] = sum(max(r['events'], 0) for r in rows if not r['path'].startswith('/ga/remote') ); row['requests'] = len(rows)
    row['label'] = label; cells[mode].append(row)
samples = sorted(c for rs in cells.values() for r in rs for c in r['calib_samples']); ref = samples[max(0, len(samples) // 20)]  # 5th percentile of all valid calibration samples = 'unloaded' reference   # fastest calibration seen anywhere = "idle" reference
out = {'reference_calib_ns': ref, 'modes': {}}
def med(rs, f): return statistics.median(f(r) for r in rs)
for mode, rs in cells.items():
    n = lambda r: r['events']
    corr = lambda r: ref / r['calib_mean']          # <1 when the guest was slowed by contention
    out['modes'][mode] = {
        'runs': len(rs), 'events': rs[0]['events'],
        'cpu_us_per_event_app_raw': med(rs, lambda r: r['cpu_total_ms'] * 1000 / n(r)),
        'cpu_us_per_event_app_corrected': med(rs, lambda r: r['cpu_total_ms'] * 1000 / n(r) * corr(r)),
        'cpu_us_per_event_gms_corrected': med(rs, lambda r: r['gms_cpu_ms'] * 1000 / n(r) * corr(r)),
        'cpu_us_per_event_replay_phase_corrected': med(rs, lambda r: r['cpu_replay_ms'] * 1000 / n(r) * corr(r)),
        'cpu_spread_pct': 100 * (max(r['cpu_total_ms'] * corr(r) for r in rs) - min(r['cpu_total_ms'] * corr(r) for r in rs)) / max(1, med(rs, lambda r: r['cpu_total_ms'] * corr(r))),
        'alloc_bytes_per_event_total': med(rs, lambda r: r['alloc_total'] / n(r)), 'alloc_bytes_per_event_replay': med(rs, lambda r: r['alloc_replay'] / n(r)),
        'track_us_p50': med(rs, lambda r: r['lat_p50_us']), 'track_us_p95': med(rs, lambda r: r['lat_p95_us']), 'track_us_p99': med(rs, lambda r: r['lat_p99_us']), 'track_us_max': med(rs, lambda r: r['lat_max_us']),
        'pss_peak_mb': med(rs, lambda r: r['pss_peak_kb'] / 1024), 'pss_growth_mb': med(rs, lambda r: (r['pss_peak_kb'] - r['pss_start_kb']) / 1024),
        'java_peak_mb': med(rs, lambda r: r['java_peak_kb'] / 1024), 'native_peak_mb': med(rs, lambda r: r['native_peak_kb'] / 1024),
        'init_cpu_ms': med(rs, lambda r: r.get('init_cpu_ms', float('nan'))), 'init_alloc_kb': med(rs, lambda r: r.get('init_alloc_kb', float('nan'))), 'disk_kb_after': med(rs, lambda r: r.get('disk_kb', -1)),
        'gc_in_replay': med(rs, lambda r: r['gc_replay']),
        'wire_bytes_per_delivered_event': med(rs, lambda r: (r['wire_body'] / r['delivered']) if r['delivered'] else float('nan')),
        'wire_with_headers_per_delivered': med(rs, lambda r: ((r['wire_body'] + r['wire_hdr']) / r['delivered']) if r['delivered'] else float('nan')),
        'delivered_share_pct': med(rs, lambda r: 100 * r['delivered'] / n(r)), 'requests': med(rs, lambda r: r['requests']),
        'host_load_range': [min(r['host_load'] for r in rs), max(r['host_load'] for r in rs)],
    }
(R / (OUTNAME + '.json')).write_text(json.dumps(out, indent=1))
print(f"{'mode':20}{'runs':>5}{'cpu_app':>9}{'cpu_gms':>9}{'alloc/ev':>10}{'p99us':>7}{'pss+MB':>8}{'wire B':>9}{'deliv%':>8}{'spread%':>8}")
for m, v in out['modes'].items():
    print(f"{m:20}{v['runs']:>5}{v['cpu_us_per_event_app_corrected']:>9.1f}{v['cpu_us_per_event_gms_corrected']:>9.1f}{v['alloc_bytes_per_event_total']:>10.0f}{v['track_us_p99']:>7.0f}{v['pss_growth_mb']:>8.1f}{v['wire_bytes_per_delivered_event']:>9.1f}{v['delivered_share_pct']:>8.1f}{v['cpu_spread_pct']:>8.1f}")
