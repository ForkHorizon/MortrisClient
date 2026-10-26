"""Per-thread CPU attribution for the Unity probe -> results/unity_threads.json. Categories: render (UnityGfxDeviceW), main (UnityMain), sdk workers (Thread-N, Background Job, .NET pool), runtime (GC/JIT/binder/other)."""
import json, os, re, statistics as st
from collections import defaultdict
from pathlib import Path
R = Path(__file__).resolve().parent / 'results'; rows = defaultdict(list)
def cat(name):
    if name.startswith('UnityGfxDeviceW'): return 'render'
    if name.startswith('UnityMain'): return 'main'
    if re.match(r'Thread-\d+$', name) or name.startswith('Background Job') or name.startswith('.NET') or name.startswith('ThreadPool'): return 'sdk_workers'
    return 'runtime_other'
for d in sorted((R / os.environ.get('UDIR', 'unity')).glob('*_r*')):
    f = d / 'perf.txt'
    if not f.exists(): continue
    t = f.read_text(); m = re.search(r'V7PERF threads mode=(\S+) replay_ms=(\d+) top=(\S*)', t); r = re.search(r'V7PERF result (.*)', t)
    if not m or not r: continue
    kind = d.name.split('_')[1]; mode = d.name.split('_')[0]; ev = int(re.search(r'events=(\d+)', r.group(1)).group(1)); tot = defaultdict(int)
    for tid, name, v in re.findall(r'(\d+):(.*?)=(\d+)(?=;\d+:|$)', m.group(3)): tot[cat(name)] += int(v)
    rows[(kind, mode)].append(dict(tot, events=ev, replay_ms=int(m.group(2))))
out = {}
for (kind, mode), rs in sorted(rows.items()):
    ev = rs[0]['events']; out[f'{kind}/{mode}'] = {'runs': len(rs), 'events': ev, 'replay_s': st.median(r['replay_ms'] for r in rs) / 1000, **{c + '_ticks_all_runs': [r.get(c, 0) for r in rs] for c in ('render', 'main', 'sdk_workers', 'runtime_other')}}
for kind in ('burst', 'paced'):
    b = out.get(f'{kind}/none')
    for mode in ('v1', 'v7'):
        c = out.get(f'{kind}/{mode}')
        if not (b and c): continue
        med = lambda x: st.median(x)
        c['sdk_workers_us_per_event'] = med(c['sdk_workers_ticks_all_runs']) * 10000 / c['events'] - med(b['sdk_workers_ticks_all_runs']) * 10000 / b['events'] * 0
        c['main_thread_extra_us_per_event'] = (med(c['main_ticks_all_runs']) - med(b['main_ticks_all_runs'])) * 10000 / c['events']
        c['render_ticks_median'] = med(c['render_ticks_all_runs']); c['render_ticks_none'] = med(b['render_ticks_all_runs'])
        c['sdk_total_us_per_event'] = c['sdk_workers_us_per_event'] + max(c['main_thread_extra_us_per_event'], 0)
(R / (os.environ.get('UDIR', 'unity') + '_threads.json')).write_text(json.dumps(out, indent=1))
for k, v in out.items(): print(k.ljust(12), 'runs', v['runs'], 'render', v['render_ticks_all_runs'], 'main', v['main_ticks_all_runs'], 'sdk_workers', v['sdk_workers_ticks_all_runs'], 'sdk us/ev', round(v.get('sdk_total_us_per_event', float('nan')), 0))
