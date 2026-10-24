#!/usr/bin/env python3
"""results/<set>/<label>/prof.txt -> results/<set>/PROFILE_TABLES.md. Per-event values = stage totals / events tracked in the scenario.
Stages are inclusive and nest (see unity/V7Prof.cs); wall includes blocking, cpu is thread CPU time."""
import sys, os, re, glob
st = sys.argv[1] if len(sys.argv) > 1 else 'emu'
root = f'results/{st}'; runs = {}
for d in sorted(glob.glob(f'{root}/*/prof.txt')):
    label = d.split('/')[-2]; stages = {}; counters = {}; summ = {}
    for l in open(d):
        l = l.strip()
        if l.startswith('summary '): summ = dict(re.findall(r'(\w+)=(\S+)', l))
        elif l.startswith('S|'): _, n, c, w, cpu, a = l.split('|'); stages[n] = (int(c), int(w), int(cpu), int(a))
        elif l.startswith('C|'): _, n, v = l.split('|'); counters[n] = int(v)
        elif l.startswith('db_events'): summ.update(dict(re.findall(r'(\w+)=(\S+)', l)))
    runs[label] = (summ, stages, counters)
out = [f'# Profiling tables ({st})\n', 'Per event = stage total / events in scenario. Times in µs. cpu = thread CPU, wall = elapsed incl. blocking. Stages nest (inclusive).\n']
def f(x, d=1): return f'{x:.{d}f}'
for label, (s, stg, c) in runs.items():
    ev = max(1, int(s.get('events', 1)))
    out.append(f'\n## {label}\n')
    tick = 10000  # µs per /proc tick
    out.append(f"events={ev}, scenario_ms={s.get('scenario_ms')}, process CPU: scenario {int(s.get('cpu_ticks_scenario',0))*tick/ev:.0f} µs/event, drain {int(s.get('cpu_ticks_drain',0))*tick/ev:.0f} µs/event, total {int(s.get('cpu_ticks_total',0))*tick/ev:.0f} µs/event; "
               f"GC0/1/2={s.get('gc0')}/{s.get('gc1')}/{s.get('gc2')}; Track µs p50/p95/p99={s.get('track_us_p50')}/{s.get('track_us_p95')}/{s.get('track_us_p99')}; frame ms p99={s.get('frame_ms_p99')}; "
               f"Unity main-thread GC alloc/event={int(s.get('unity_gc_alloc_bytes_main_frames',0))/ev:.0f} B ({int(s.get('unity_gc_alloc_count_main_frames',0))/ev:.2f} allocs); ART(Java) alloc/event={int(s.get('art_bytes_allocated',0))/ev:.0f} B, ART GCs={s.get('art_gc_count')}; PSS start/peak MB={int(s.get('pss_start_kb',0))/1024:.0f}/{int(s.get('pss_peak_kb',0))/1024:.0f}; db_events={s.get('db_events')}, packets_v2={s.get('packets_v2')}, batches_v1={s.get('batches_v1')}\n")
    out.append('| stage | calls/event | cpu µs/event | wall µs/event | managed alloc B/event |\n|---|---|---|---|---|')
    for n, (calls, w, cpu, a) in stg.items(): out.append(f'| {n} | {f(calls/ev,2)} | {f(cpu/ev)} | {f(w/ev)} | {f(a/ev,0)} |')
    sent = c.get('bytes_v7_packets', 0) + c.get('bytes_v1_gzip_bodies', 0)
    out.append(f"\nTraffic: V7 packets {c.get('v7_packets',0)} ({c.get('bytes_v7_packets',0)} B), V1 batches {c.get('v1_batches',0)} (gzip {c.get('bytes_v1_gzip_bodies',0)} B, json {c.get('bytes_v1_json_bodies',0)} B) -> {sent/ev:.1f} B/event body; persist_calls={c.get('persist_calls')} for {ev} events (avg {c.get('persist_events',0)/max(1,c.get('persist_calls',1)):.2f} events per call)")
open(f'{root}/PROFILE_TABLES.md', 'w').write('\n'.join(out) + '\n'); print('wrote', len(runs), 'runs')
