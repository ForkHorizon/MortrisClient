"""Builds results/TABLES.md from all measured result files (numbers only, no prose)."""
import json, glob, statistics as st
from pathlib import Path
R = Path(__file__).resolve().parent / 'results'
def J(p):
    try: return json.load(open(R / p))
    except Exception: return None
out = []
def table(title, head, rows):
    out.append(f'\n### {title}\n'); out.append('| ' + ' | '.join(head) + ' |'); out.append('|' + '---|' * len(head))
    for r in rows: out.append('| ' + ' | '.join(str(x) for x in r) + ' |')
f = lambda x, d=1: ('n/a' if x is None or x != x else f'{x:,.{d}f}')
# --- android
for name, label in (('android_summary_c1', 'API 35 emulator (arm64, 6000 events/run, 3 runs; Firebase = production-mode rerun)'), ('android_summary_c2', 'API 25 emulator (arm64, 3000 events/run, 3 runs; sinks for Firebase/Adjust/Facebook)')):
    a = J(name + '.json')
    if not a: continue
    base = a['modes'].get('base_map', {}); rows = []
    for m, v in a['modes'].items():
        net = v['cpu_us_per_event_app_corrected'] - base.get('cpu_us_per_event_app_corrected', 0) if m != 'base_map' else 0
        gms = v['cpu_us_per_event_gms_corrected'] - base.get('cpu_us_per_event_gms_corrected', 0) if m != 'base_map' else 0
        rows.append([m, v['runs'], f(v['cpu_us_per_event_app_corrected'], 0), f(net, 0), f(gms, 0), f(v['alloc_bytes_per_event_total'] - base.get('alloc_bytes_per_event_total', 0), 0), f(v['pss_growth_mb'], 1), f(v['java_peak_mb'], 1), f(v['native_peak_mb'], 1), f(v['track_us_p50'], 0), f(v['track_us_p99'], 0), f(v['wire_bytes_per_delivered_event'], 1), f(v['wire_with_headers_per_delivered'], 1), f(v['delivered_share_pct'], 1), f(v['cpu_spread_pct'], 0)])
    table('Android SDKs: ' + label, ['mode', 'runs', 'app CPU us/ev (corrected)', 'net of harness baseline', 'GMS process net us/ev', 'net alloc B/ev', 'PSS growth MB', 'java peak MB', 'native peak MB', 'track p50 us', 'track p99 us', 'wire body B/ev', 'wire +hdr B/ev', 'delivered %', 'CPU spread %'], rows)
p = J('android_summary_pace2.json')
if p:
    rows = [[m, f(v['cpu_us_per_event_app_corrected'], 0), f(v['cpu_us_per_event_gms_corrected'], 0), f(v['alloc_bytes_per_event_total'], 0), f(v['pss_growth_mb'], 1), f(v['wire_bytes_per_delivered_event'], 1), f(v['delivered_share_pct'], 1), f(v['init_cpu_ms'], 0)] for m, v in p['modes'].items()]
    table('Paced replay, 2 events/s, 600 events (one run; includes idle timers)', ['mode', 'app CPU us/ev', 'GMS us/ev', 'alloc B/ev', 'PSS growth MB', 'wire B/ev', 'delivered %', 'init CPU ms'], rows)
# --- unity
u = J('unity_summary.json')
if u:
    rows = [[k, v['runs'], f(v.get('net_cpu_us_per_event_total'), 0), f(v['track_us_p50'], 1), f(v['track_us_p99'], 0), f(v['frame_ms_p99'], 1), f(v['gc_collections'], 0), f(v['mono_growth_kb'], 0), f(v['pss_growth_mb'], 1), v['packets_v2'], v['batches_v1']] for k, v in u['cells'].items()]
    table('Unity IL2CPP probe (API 35 emulator)', ['cell', 'runs', 'net CPU us/ev (vs empty player)', 'Track p50 us', 'Track p99 us', 'frame p99 ms', 'GC runs', 'mono growth KB', 'PSS growth MB', 'V7 packets', 'V1 batches'], rows)
# --- fidelity
fi = J('fidelity_fid.json')
if fi:
    table('Data fidelity (1500 real events, marker property)', ['mode', 'delivered %', 'events fully preserved %', 'properties lost %', 'lost kinds', 'strings truncated', 'type changed'], [[m, f(v['delivered_share_pct'], 1), f(v['events_fully_preserved_pct_of_delivered'], 1), f(v['properties_lost_pct'], 2), v['lost_by_value_kind'], v['strings_truncated'], v['type_changed']] for m, v in fi.items() if isinstance(v, dict)])
# --- firebase wire
rows = []
for fp in sorted(glob.glob(str(R / 'firebase_wire/*.json'))):
    d = json.load(open(fp)); pb = json.loads(d['pbcount'].split('} {')[0] + '}') if '} {' in d['pbcount'] else json.loads(d['pbcount'])
    rows.append([d['tag'], pb['uploads'], pb['events'], f(pb['gz_bytes_per_event'], 1), f(pb['raw_bytes_per_event'], 0), f(pb['events'] / max(pb['uploads'], 1), 0)])
if rows: table('Firebase Analytics 23.0.0, real uploads captured (API 25, TLS sink)', ['run', 'uploads', 'events', 'gzip body B/ev', 'raw proto B/ev', 'events/upload'], rows)
# --- host
hs = [json.load(open(x)) for x in sorted(glob.glob(str(R / 'host_clean/all_*.json')))]
if hs:
    g = lambda k: st.median(h[k] for h in hs)
    table('Host (macOS arm64, .NET 10) - V7 encoder vs V1 gzip, all 974,689 real events, median of %d runs' % len(hs), ['metric', 'V7', 'V1 (gzip fast)'], [
        ['wire bytes / event', f(g('v7_bytes_per_event'), 2), f(g('v1_gzip_bytes_per_event'), 1)], ['CPU ns / event (thread CPU)', f(g('v7_cpu_ns_per_event'), 0), f(g('v1_gzip_cpu_ns_per_event'), 0)],
        ['CPU ns / event load-corrected', f(g('v7_cpu_ns_per_event_chunk_median_load_corrected'), 0), '-'], ['alloc bytes / event', f(g('v7_alloc_bytes_per_event'), 0), f(g('v1_gzip_alloc_bytes_per_event'), 0)],
        ['of which JSON parse (CPU ns / alloc B)', f(g('parse_only_cpu_ns_per_event'), 0) + ' / ' + f(g('parse_only_alloc_bytes_per_event'), 0), '-'], ['p50 / p95 / p99 CPU ns per event (per 100-event batch)', f(g('p50_v7_cpu_ns_per_event'), 0) + ' / ' + f(g('p95_v7_cpu_ns_per_event'), 0) + ' / ' + f(g('p99_v7_cpu_ns_per_event'), 0), '-'],
        ['GC gen0 / gen2 collections', f(g('gc_gen0'), 0) + ' / ' + f(g('gc_gen2'), 0), '-']])
gd = [J(f'host/go_decode_{i}.json') for i in (1, 2, 3)]; gv = J('host/go_v1_1.json')
if gd[0] and gv:
    table('Server decode (Go, GOMAXPROCS=1, holdout 763,661 events)', ['path', 'CPU ns/event', 'alloc B/event', 'p99 ns', 'RSS MB'], [['V7 packet decode', f(st.median(d['decode_cpu_ns_per_event'] for d in gd), 0), f(gd[0]['alloc_bytes_per_event'], 0), f(gd[0]['p99_ns'], 0), f(gd[0]['maxrss_mb'], 0)], ['V1 gunzip + DecodeBatchIngestRequest', f(gv['v1_decode_cpu_ns_per_event'], 0), 'n/a', f(gv['p99_ns'], 0), f(gv['maxrss_mb'], 0)]])
rows = []
for mode in ('v1', 'v7'):
    for kind in ('seq', 'par6'):
        rs = [J(f'server/{mode}_{kind}_r{i}/result.json') for i in (1, 2, 3)]; rs = [r for r in rs if r]
        if rs: rows.append([mode, kind, len(rs), f(st.median(r['server_cpu_us_per_event'] for r in rs), 0), f(st.median(r['postgres_cpu_us_per_event'] for r in rs), 0), f(st.median(r['server_rss_peak_mb'] for r in rs), 0), f(st.median(r['postgres_rss_peak_mb'] for r in rs), 0), sum(r['errors'] for r in rs), f(st.median(r['db_events'] for r in rs), 0)])
if rows: table('Server end-to-end ingest (Go server + PostgreSQL, ~41k real events, rate-limited to 25 req/s)', ['mode', 'concurrency', 'runs', 'server CPU us/ev', 'PostgreSQL CPU us/ev', 'server RSS MB', 'PG RSS MB', 'errors', 'events stored'], rows)
(R / 'TABLES.md').write_text('\n'.join(out)); print('\n'.join(out))
