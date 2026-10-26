"""Aggregates results/sdk-runs/*.jsonl (collector logs) and compares with V1/V7 on the SAME 600 replay events.
Observed events = events whose name is one of the replay names (SDK housekeeping events counted separately).
Wire bytes: cleartext HTTP at the host socket (request headers + body + response). TLS/DNS/TCP handshake NOT included."""
import json, re, statistics, sys, importlib.util
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent; RUNS = HERE.parent / 'results' / (sys.argv[1] if len(sys.argv) > 1 else 'sdk-runs')
REPLAY_FILE = sys.argv[2] if len(sys.argv) > 2 else None; OUTNAME = sys.argv[3] if len(sys.argv) > 3 else 'sdk-compare.json'
spec = importlib.util.spec_from_file_location('sb', HERE / 'synth_bench.py'); sb = importlib.util.module_from_spec(spec); spec.loader.exec_module(sb)
NAMES = {json.loads(l)['name'] for l in open(REPLAY_FILE)} if REPLAY_FILE else set(sb.NAMES)

def run_stats(path):
    reqs = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    ev = [r for r in reqs if r['events'] > 0 or '/events' in r['path'] or r['path'] == '/amp']
    cats = reqs[-1]['cats'] if reqs else {}
    obs = sum(v for k, v in cats.items() if k in NAMES) or (cats.get('design', 0))
    ga_design = cats.get('design', 0)
    obs = sum(v for k, v in cats.items() if k in NAMES) if any(k in NAMES for k in cats) else ga_design
    total_events = sum(cats.values())
    ts = [r['t'] for r in ev]
    log = (path.with_suffix('.logcat.txt')).read_text() if path.with_suffix('.logcat.txt').exists() else ''
    m = re.search(r'track_mean_us=(\d+) track_max_us=(\d+)', log)
    return dict(requests=len(reqs), event_requests=len(ev), header_bytes=sum(r['req_header_bytes'] for r in reqs), body_bytes=sum(r['req_body_bytes'] for r in reqs),
                resp_bytes=sum(r['resp_bytes'] for r in reqs), decoded_bytes=sum(r['decoded_body_bytes'] for r in reqs), observed_target_events=obs, all_events_observed=total_events,
                events_per_request=[r['events'] for r in ev], request_gaps_s=[round(b - a, 2) for a, b in zip(ts, ts[1:])],
                gzip=any(r['content_encoding'] == 'gzip' for r in reqs), track_mean_us=int(m.group(1)) if m else None, track_max_us=int(m.group(2)) if m else None)

def main():
    by = defaultdict(list)
    for p in sorted(RUNS.glob('*.jsonl')):
        if '.sample' in p.name: continue
        mode, corpus, rep = re.match(r'(.+)-([a-z_]+)-r(\d+)\.jsonl', p.name).groups(); by[(mode, corpus)].append(run_stats(p))
    out = {'sdk': {}, 'mortris': {}}
    for (mode, corpus), rs in sorted(by.items()):
        def agg(k): v = [r[k] for r in rs]; return dict(min=min(v), median=statistics.median(v), max=max(v))
        wire = [r['header_bytes'] + r['body_bytes'] + r['resp_bytes'] for r in rs]
        out['sdk'][f'{mode}/{corpus}'] = dict(runs=len(rs), observed_target_events=agg('observed_target_events'), all_events_observed=agg('all_events_observed'),
            requests=agg('requests'), body_bytes=agg('body_bytes'), header_bytes=agg('header_bytes'), wire_bytes_both_directions=dict(min=min(wire), median=statistics.median(wire), max=max(wire)),
            body_B_per_observed_event_median=statistics.median([r['body_bytes'] / max(1, r['observed_target_events']) for r in rs]),
            wire_B_per_observed_event_median=statistics.median([w / max(1, r['observed_target_events']) for w, r in zip(wire, rs)]),
            gzip=rs[0]['gzip'], track_mean_us=agg('track_mean_us') if rs[0]['track_mean_us'] is not None else None,
            example_events_per_request=rs[0]['events_per_request'][:12], example_request_gaps_s=rs[0]['request_gaps_s'][:12])
    # Mortris V1/V7 on the same events (2 installs x 300; V7 catalog+dict32 trained on synthetic seed 11 only)
    for corpus, session_len in (() if REPLAY_FILE else (('low', (15, 60)), ('high', (15, 60)))):
        train = sb.rebatch(sb.corpus(corpus, 11, 20, 300, session_len), 100)
        c = sb.Catalog.train(sb.PROJECT, train); d32 = sb.z.train_dictionary(32768, sb.samples(c, train), level=1)
        for cap in (10, 100):
            r = sb.measure(c, d32, sb.rebatch(sb.corpus(corpus, 33, 2, 300, session_len), cap))
            out['mortris'][f'{corpus}/batch{cap}'] = dict(events=r['events'], v1_gzip1_body=r['bytes']['v1_gzip1'], v7_seq_body=r['bytes']['v7_seq'], v7_full_uuid_body=r['bytes']['v7_full_uuid'],
                v1_B_event=r['B_event']['v1_gzip1'], v7_B_event=r['B_event']['v7_seq'], setup_bytes_not_included=len(c.data) + 32768 + r['alias_setup_bytes'], batches=r['batches'])
    (HERE.parent / 'results' / OUTNAME).write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))
if __name__ == '__main__': main()
