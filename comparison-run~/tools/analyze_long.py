#!/usr/bin/env python3
"""10-minute play sessions on the phone (5 events/s, 3000 events, SDK's own timers). Net CPU against the `none` session, PSS, GC, latency, wire."""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); import wire
R = Path(__file__).resolve().parent.parent / 'results/phone_long'
def load(n):
    d = R / n
    try: return json.load(open(d / 'result.json')), json.load(open(d / 'run.json')), d
    except Exception: return None
base = load('none_10min')
print('| SDK | CPU net, мс на событие (сессия 10 мин) | CPU net, % одного ядра | Track p50/p99 мкс | PSS пик МБ | Mono GC0 | ART аллокации КБ/событие | байт/событие вверх | с TLS | запросов | соединений | доставлено |')
print('|---|---|---|---|---|---|---|---|---|---|---|---|')
for n, name in (('none_10min', 'нет SDK'), ('mortris_v8_10min', 'Mortris V8'), ('mortris_v1_10min', 'Mortris V1'), ('ga_10min', 'GameAnalytics 7.2.0')):
    x = load(n)
    if not x: continue
    r, run, d = x
    secs = r['scenario_ms'] / 1000; ev = r['events']
    net = None
    if base and n != 'none_10min':
        b = base[0]; net = (r['cpu_ticks_scenario'] - b['cpu_ticks_scenario'] * secs / (b['scenario_ms'] / 1000) + r['cpu_ticks_tail'] - b['cpu_ticks_tail'] * r['tail_s'] / max(b['tail_s'], 1)) * 10
    w = None
    if (d / 'wire.jsonl').exists() and (d / 'wire.jsonl').stat().st_size:
        dn = (run['db1'] - run['db0']) if run.get('db0') is not None else (run['final_stats'].get('events') or ev)
        w = wire.summarize(str(d / 'wire.jsonl'), 'mortris_v8' if 'mortris' in n else 'ga', dn or ev)
    dl = (run['db1'] - run['db0']) if run.get('db0') is not None else run['final_stats'].get('events')
    print(f"| {name} | {'—' if net is None else f'{net / ev:.3f}'} | {'—' if net is None else f'{net / 10 / (secs + r['tail_s']) :.2f}'} | {r['track_us']['p50']:.0f}/{r['track_us']['p99']:.0f} | {r['mem_peak'][0] / 1024:.0f} | {r['gc_mono'][0]:.0f} | {r.get('art_bytes_scenario', 0) / ev / 1024:.2f} | "
          f"{w['per_event_up']:.1f} | {w['per_event_with_tls']:.1f} | {w['requests']} | {w['connections']} | {dl}/{ev} |" if w else f"| {name} | {'—' if net is None else f'{net / ev:.3f}'} | — | {r['track_us']['p50']:.0f}/{r['track_us']['p99']:.0f} | {r['mem_peak'][0] / 1024:.0f} | {r['gc_mono'][0]:.0f} | {r.get('art_bytes_scenario', 0) / ev / 1024:.2f} | — | — | — | — | — |")
