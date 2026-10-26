"""Process-wide CPU time and ART managed allocation per SDK (Android emulator, Java/ART). Baseline = same replay parsing without any SDK.
CPU is process CPU ms (all threads); alloc is cumulative art.gc.bytes-allocated (managed Java heap only, NOT native). Not comparable with Unity/IL2CPP GC numbers."""
import json, re, statistics
from collections import defaultdict
from pathlib import Path
R = Path(__file__).resolve().parent.parent / 'results'; D = R / 'sdk-runs-perf'
by = defaultdict(list)
for f in sorted(D.glob('*.logcat.txt')):
    mode = f.name.split('-puzzle')[0]; m = re.search(r'perf (.*)', f.read_text())
    if m: by[mode].append({k: int(v) for k, v in (x.split('=') for x in m.group(1).split())})
def med(mode, k): return statistics.median(r[k] for r in by[mode])
out = {'runs': {k: len(v) for k, v in by.items()}, 'median_raw': {m: {k: med(m, k) for k in by[m][0]} for m in by}, 'per_event_net': {}}
for sdk, base in (('amplitude_default', 'base_parse'), ('ga_default', 'base_map')):
    if sdk in by and base in by:
        n = med(sdk, 'events')
        out['per_event_net'][sdk] = {
            'init_cpu_ms_net': med(sdk, 'init_cpu_ms') - med(base, 'init_cpu_ms'), 'init_alloc_KB_net': (med(sdk, 'init_alloc') - med(base, 'init_alloc')) / 1024,
            'replay_cpu_ms_net': med(sdk, 'total_cpu_ms') - med(base, 'total_cpu_ms'), 'cpu_us_per_event_net': (med(sdk, 'total_cpu_ms') - med(base, 'total_cpu_ms')) * 1000 / n,
            'alloc_B_per_event_net': (med(sdk, 'total_alloc') - med(base, 'total_alloc')) / n, 'gc_count_net': med(sdk, 'total_gc') - med(base, 'total_gc'),
            'min_max_cpu_ms_sdk': [min(r['total_cpu_ms'] for r in by[sdk]), max(r['total_cpu_ms'] for r in by[sdk])],
            'min_max_alloc_sdk': [min(r['total_alloc'] for r in by[sdk]), max(r['total_alloc'] for r in by[sdk])]}
(R / 'sdk-perf-puzzle.json').write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))
