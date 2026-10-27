#!/usr/bin/env python3
"""Tables of the big emulator run: #0127 separation, network drain matrix, Wi-Fi flapping, 30-minute offline. Usage: analyze_big.py > results/BIG_TABLES.md"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); import wire
R = Path(__file__).resolve().parent.parent / 'results'
def load(d):
    try: return json.loads((d / 'run.json').read_text())
    except Exception: return None
def reqs(d):
    out = []
    p = d / 'wire.jsonl'
    if not p.exists(): return out
    for l in open(p):
        r = json.loads(l)
        if not r.get('closed') and r['path'] != '/__stats': out.append(r)
    return out
def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '|' + '|'.join(['---'] * len(headers)) + '|'] + ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows])
def delivered(run):
    if run and run.get('db0') is not None and run.get('db1') is not None: return run['db1'] - run['db0']
    return (run or {}).get('final_stats', {}).get('events')
def sdk_of(label): return 'mortris_v1' if 'v1' in label else 'mortris_v8'

if (R / 'sep0127b').exists():
    rows = []
    for d in sorted((R / 'sep0127b').iterdir()):
        run = load(d)
        if not run: continue
        pk = [r for r in reqs(d) if r['path'].endswith('/packet')]; t = [round(r['t']) for r in pk]
        gaps = [t[i + 1] - t[i] for i in range(len(t) - 1)]
        rows.append([d.name, delivered(run), len(pk), t[0] if t else '-', t[-1] if t else '-', max(gaps) if gaps else '-', sum(1 for r in reqs(d) if r['status'] == 429), run.get('settled')])
    print('## #0127: midcore, каталог 1000+ форм и обученный словарь, лимиты по умолчанию (T4) и снятые (T5)\n'); print(table(['ячейка', 'доставлено', 'пакетов', 'первый пакет, с', 'последний, с', 'макс. пауза между пакетами, с', '429', 'как закончили'], rows))

if (R / 'bignet').exists():
    rows = []
    for d in sorted((R / 'bignet').glob('drain_*')):
        run = load(d)
        if not run: continue
        rq = reqs(d); pk = [r for r in rq if r['path'].endswith('/packet') or r['path'].endswith('/batch')]
        if not pk: rows.append([d.name, delivered(run), 0, '-', '-', '-', '-', run.get('settled')]); continue
        w = wire.summarize(str(d / 'wire.jsonl'), sdk_of(d.name), delivered(run) or 1)
        ok = [r for r in pk if r['status'] == 200]; first, last = min(r['t'] for r in pk), max(r['t'] for r in pk)
        rows.append([d.name, delivered(run), len(pk), f'{last - first:.0f}', len(pk) - len(ok), w['connections'], f"{w['per_event_up']:.1f}", f"{w['per_event_with_tls']:.1f}", run.get('settled')])
    print('\n## Разгребание бэклога 10 000 событий по сетям (потери 10/4/2/1%; пачка 100/200/500/адаптивно; V1 для сравнения)\n')
    print(table(['ячейка', 'доставлено', 'запросов с данными', 'время от первого до последнего, с', 'не-200', 'соединений', 'вверх Б/событие', 'с TLS Б/событие', 'как закончили'], [r if len(r) == 9 else r + ['-'] * (9 - len(r)) for r in rows]))
    rows = []
    for d in sorted((R / 'bignet').glob('flap_*')):
        run = load(d)
        if not run: continue
        ev = run.get('wifi_events') or []; t0 = run.get('collector_t0'); rq = reqs(d); stamps = [(t0 + r['t'], r) for r in rq] if t0 else []
        offs = [(ev[i][1], ev[i + 1][1]) for i in range(0, len(ev) - 1, 2) if ev[i][0] == 'off' and ev[i + 1][0] == 'on']
        during = sum(1 for ts, r in stamps if any(a <= ts <= b for a, b in offs))
        after = []
        for a, b in offs:
            nxt = [ts - b for ts, r in stamps if ts >= b]
            if nxt: after.append(min(nxt))
        rows.append([d.name, delivered(run), len(rq), len(offs), during, f'{min(after):.1f}…{max(after):.1f}' if after else '-', run.get('settled')])
    if rows:
        print('\n## Мигание сети (Wi-Fi и данные выкл 20 с / вкл 20 с, 8 циклов, 5 событий/с)\n')
        print(table(['ячейка', 'доставлено', 'запросов', 'циклов выкл', 'запросов во время «выкл»', 'до первого запроса после «вкл», с (мин…макс)', 'как закончили'], rows))
    rows = []
    for d in sorted((R / 'bignet').glob('offline30_*')):
        run = load(d)
        if not run: continue
        rq = [r for r in reqs(d) if r['path'].endswith('/packet') or r['path'].endswith('/batch')]
        back = run.get('backend_back_at') or 0
        rows.append([d.name, delivered(run), len(rq), f"{(min(r['t'] for r in rq)) :.0f}" if rq else '-', f"{(max(r['t'] for r in rq) - min(r['t'] for r in rq)) :.0f}" if rq else '-', run.get('settled')])
    if rows:
        print('\n## Оффлайн 30 минут (18 000 событий), затем сервер возвращается\n')
        print(table(['ячейка', 'доставлено', 'запросов с данными', 'первый запрос после возврата, с от старта сборщика', 'длительность разгребания, с', 'как закончили'], rows))
