#!/usr/bin/env python3
"""Stage tables from a profiling set (tools/matrix_profile.py). Usage: analyze_profile.py SETNAME [group-prefix] > results/SETNAME/PROFILE_TABLES.md
For every cell group (label without the _rN suffix): per tracked event, per stage: calls, wall us, thread-CPU us, managed heap growth (B), and the share of the biggest stage; the Java
side's stages; counters; thread CPU of the process; for `init_*` groups the first-use timeline (what ran when, on which thread). Values are means over the repetitions."""
import json, re, statistics, sys
from collections import defaultdict
from pathlib import Path
R = Path(__file__).resolve().parent.parent / 'results' / sys.argv[1]; prefix = sys.argv[2] if len(sys.argv) > 2 else ''
def parse(text):
    stages, counters, trace, java = {}, {}, [], {}
    for line in (text or '').splitlines():
        f = line.split('|')
        if f[0] == 'S' and len(f) >= 9: stages[f[1]] = dict(calls=int(f[2]), wall=int(f[3]), cpu=int(f[4]), heap=int(f[5]), max=int(f[6]), p50=int(f[7]), p99=int(f[8]))
        elif f[0] == 'C': counters[f[1]] = int(f[2])
        elif f[0] == 'T': trace.append((f[1], int(f[2]), int(f[3]), int(f[4])))
        elif f[0] == 'J':
            try: java = json.loads(line[2:])
            except Exception: pass
    return stages, counters, trace, java
groups = defaultdict(list)
for d in sorted(R.iterdir()):
    if not d.name.startswith(prefix) or not (d / 'result.json').exists(): continue
    m = re.match(r'^(.*)_r(\d+)$', d.name)
    if not m: continue
    try: groups[m.group(1)].append(json.load(open(d / 'result.json')))
    except Exception: pass
def mean(v): v = [x for x in v if x is not None]; return statistics.mean(v) if v else 0
def table(rows, headers):
    out = ['| ' + ' | '.join(headers) + ' |', '|' + '|'.join(['---'] * len(headers)) + '|']
    return '\n'.join(out + ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows])
for name, results in sorted(groups.items()):
    key = 'prof_init' if name.startswith('init_') else 'prof_scenario'
    parsed = [parse(r.get(key)) for r in results if r.get(key)]
    if not parsed: continue
    events = [max(1, r.get('tracked') or r.get('events') or 1) for r in results if r.get(key)]
    print(f'\n## {name} ({len(parsed)} повтора)\n')
    r0 = results[0]
    print(f"Событий: {mean(events):.0f}; длительность сценария {mean([r.get('scenario_ms') for r in results]) / 1000:.1f} с; CPU приложения за сценарий {mean([r.get('cpu_ticks_scenario') for r in results]) * 10:.0f} мс, за хвост {mean([r.get('cpu_ticks_tail') for r in results]) * 10:.0f} мс; "
          f"Mono GC0 {mean([r['gc_mono'][0] for r in results]):.0f}; ART {mean([r.get('art_bytes_scenario') for r in results]) / 1024:.0f} КБ; Unity GC alloc {mean([r.get('unity_gc_alloc_bytes_frames') for r in results]) / 1024:.0f} КБ\n")
    names = sorted({n for s, _, _, _ in parsed for n in s})
    rows = []
    for n in names:
        per = [(s.get(n) or dict(calls=0, wall=0, cpu=0, heap=0, max=0, p50=0, p99=0), ev) for (s, _, _, _), ev in zip(parsed, events)]
        wall_total = mean([p['wall'] for p, _ in per]); rows.append((wall_total, [n, f"{mean([p['calls'] / ev for p, ev in per]):.2f}", f"{mean([p['wall'] / ev for p, ev in per]):.1f}", f"{mean([p['cpu'] / ev for p, ev in per]):.1f}",
                                                                             f"{mean([p['heap'] / ev for p, ev in per]):.0f}", f"{mean([p['p50'] for p, _ in per]):.0f}", f"{mean([p['p99'] for p, _ in per]):.0f}", f"{mean([p['max'] for p, _ in per]):.0f}"]))
    print(table([r for _, r in sorted(rows, key=lambda x: -x[0])], ['стадия', 'вызовов/событие', 'wall мкс/событие', 'CPU мкс/событие', 'рост кучи Б/событие', 'p50 мкс', 'p99 мкс', 'max мкс']))
    counters = defaultdict(list)
    for _, c, _, _ in parsed:
        for k, v in c.items(): counters[k].append(v)
    if counters: print('\nСчётчики: ' + ', '.join(f'{k}={mean(v):.0f}' for k, v in sorted(counters.items())))
    java = defaultdict(list)
    for _, _, _, j in parsed:
        for k, v in j.items(): java[k].append(v)
    if java:
        print('\nJava-очередь (за сценарий, среднее по повторам):\n')
        print(table([[k, f"{mean([x[0] for x in v]):.0f}", f"{mean([x[1] for x in v]) / 1000:.0f}", f"{mean([x[2] for x in v]) / 1000:.0f}", f"{mean([x[3] for x in v]) / 1024:.0f}", f"{mean([x[4] for x in v]) / 1000:.0f}"] for k, v in sorted(java.items())],
                    ['этап', 'вызовов', 'wall мкс всего', 'CPU мкс всего (итоги)', 'ART КБ всего (итоги)', 'max мкс']))
    threads = defaultdict(list)
    for r in results:
        for k, v in (r.get('threads_scenario') or {}).items(): threads[re.sub(r'^\d+:', '', k)].append(v * 10)
    if threads: print('\nПотоки процесса за сценарий (мс CPU): ' + ', '.join(f'{k}={mean(v):.0f}' for k, v in sorted(threads.items(), key=lambda x: -mean(x[1]))[:8]))
    if name.startswith('init_') and parsed[0][2]:
        print('\nТаймлайн первого запуска (мс от сброса таймеров; поток; стадия; длительность мс):\n')
        tr = sorted(parsed[0][2], key=lambda t: t[2])[:60]
        print(table([[f'{t[2] / 1000:.1f}', t[1], t[0], f'{t[3] / 1000:.2f}'] for t in tr], ['начало мс', 'поток', 'стадия', 'длит. мс']))
