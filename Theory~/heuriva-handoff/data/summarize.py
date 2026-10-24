#!/usr/bin/env python3
"""Per-candidate summary from all_measurements.csv, offline. Stores are cumulative (each night copied the previous
store), so rows are de-duplicated by (ctx, cand, run_id, repeat). Protocols are never mixed: grouped by ctx.
bytes/event = pooled bpe; CPU ratio = enc_ns/ref_enc_ns per repeat, mean and sample SD."""
import csv, json, statistics as st, collections, sqlite3, glob
ctxproto = {}
for p in glob.glob('*.knowledge.sqlite3'):
    c = sqlite3.connect(f'file:{p}?mode=ro&immutable=1', uri=True)
    try: ctxproto.update({r[0]: r[1] for r in c.execute('select ctx,protocol from contexts')})
    except sqlite3.Error: pass
seen, g = set(), collections.defaultdict(list)
for r in csv.DictReader(open('all_measurements.csv')):
    k = (r['ctx'], r['cand'], r['run_id'], r['repeat'])
    if k in seen or r['ok'] != '1': continue
    seen.add(k); g[(ctxproto.get(r['ctx'], r['ctx']), r['cand'])].append(r)
rows = []
for (proto, cand), rs in g.items():
    p = json.loads(cand)['params']
    bpe = st.mean(float(r['bpe']) for r in rs); ref = float(rs[0]['ref_bpe'])
    e = [float(r['enc_ns']) / float(r['ref_enc_ns']) for r in rs]; d = [float(r['dec_ns']) / float(r['ref_dec_ns']) for r in rs]
    sd = lambda x: st.stdev(x) if len(x) > 1 else ''
    rows.append(dict(protocol=proto, batch=p['batch_size'], dict_kib=p['dictionary_kib'], model=p['model'], batching=p['batching'],
        rows=len(rs), runs=len({r['run_id'] for r in rs}), bpe=round(bpe, 3), vs_m7_pct=round((bpe / ref - 1) * 100, 2),
        enc_ratio=round(st.mean(e), 4), enc_sd=sd(e) and round(sd(e), 4), dec_ratio=round(st.mean(d), 4), dec_sd=sd(d) and round(sd(d), 4)))
rows.sort(key=lambda r: (r['protocol'], r['bpe']))
w = csv.DictWriter(open('candidate_summary.csv', 'w', newline=''), fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
print(len(rows), 'candidates;', len(seen), 'unique rows')
