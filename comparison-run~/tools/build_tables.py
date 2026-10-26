#!/usr/bin/env python3
"""Markdown tables for REPORT.md from results/*. Usage: build_tables.py > RESULTS_TABLES.md"""
import json, math, sys
from pathlib import Path
R = Path(__file__).resolve().parent.parent / 'results'
NAMES = {'none': 'нет SDK (база)', 'noop': 'noop (JNI+JSON, без SDK)', 'mortris_v1': 'Mortris V1', 'mortris_v7': 'Mortris V7', 'mortris_v8': 'Mortris V8', 'mortris_v8c': 'Mortris V8 + новое содержание событий',
         'amplitude': 'Amplitude 2.40.1', 'amplitude_kotlin': 'Amplitude Kotlin 1.36.0', 'ga': 'GameAnalytics 7.2.0', 'firebase': 'Firebase 23.0.0', 'facebook': 'Facebook core 17.0.2', 'adjust': 'Adjust 5.4.1',
         'hyperkit_core': 'HyperKit (core)', 'hyperkit_ctx': 'HyperKit (ctx=все свойства)', 'mixpanel': 'Mixpanel 8.2.0'}
ORDER = list(NAMES)
def f(x, p=1, ci=True):
    if not x: return '—'
    return f"{x['mean']:.{p}f}" + (f" ±{x['ci95']:.{p}f}" if ci and x.get('n', 0) > 1 else '')
def table(headers, rows):
    out = ['| ' + ' | '.join(headers) + ' |', '|' + '|'.join(['---'] * len(headers)) + '|']
    out += ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows]
    return '\n'.join(out)
s = json.load(open(R / 'cpu/summary.json'))
print('## Таблица A. Сценарий B (20 событий/кадр, 3000 событий; Nothing A142, IL2CPP release, 3 повтора, среднее ±95% ДИ)\n')
rows = []
for k in ORDER:
    v = s.get(k + '|B')
    if not v: continue
    rows.append([NAMES[k], f(v.get('net_total_ms_per_ev'), 3), f(v.get('netall_app'), 3), f(v.get('netall_gms'), 3), f(v['track_p50'], 0), f(v['track_p99'], 0), f(v['frame_p99'], 1), f(v['jank33'], 1),
                 f(v['pss_peak_mb'], 0), f(v.get('delivered_share'), 2, False), f(v.get('up_per_delivered'), 1), f(v.get('total_per_delivered'), 1)])
print(table(['SDK', 'CPU net мс/событие', 'все процессы: приложение', 'GMS', 'Track p50 мкс', 'p99 мкс', 'кадр p99 мс', 'кадров >33мс', 'PSS пик МБ', 'доля доставлена', 'байт/событие вверх', 'байт/событие всего с TLS'], rows))
print('\n## Таблица A3. Сборки мусора и аллокации (сценарий B; Mono GC0 за прогон, Java/ART аллокации КБ на событие; в release-сборке Unity не отдаёт байты управляемых аллокаций)\n')
rows = []
for k in ORDER:
    v = s.get(k + '|B')
    if not v: continue
    rows.append([NAMES[k], f(v['gc0'], 1), f((v.get('art_bytes_per_ev') or {'mean': 0, 'ci95': 0, 'n': 1}) and {**v['art_bytes_per_ev'], 'mean': v['art_bytes_per_ev']['mean'] / 1024, 'ci95': v['art_bytes_per_ev']['ci95'] / 1024} if v.get('art_bytes_per_ev') else None, 2), f(v['art_gc'], 1), f(v['java_peak_mb'], 1), f(v['native_peak_mb'], 1), f(v['init_ms'], 0)])
print(table(['SDK', 'Mono GC0', 'ART КБ/событие', 'ART GC', 'Java heap пик МБ', 'native heap пик МБ', 'инициализация мс'], rows))
print('\n## Таблица A2. Сценарий A (10 событий/с, 400 событий, 60 с работы). Базовая нагрузка Unity в этом сценарии шумит, поэтому приведены значения за вычетом базы\n')
rows = []
for k in ORDER:
    v = s.get(k + '|A')
    if not v: continue
    rows.append([NAMES[k], f(v.get('net_total_ms_per_ev'), 2), f(v['track_p50'], 0), f(v['track_p99'], 0), f(v['pss_peak_mb'], 0), f(v.get('delivered_share'), 2, False), f(v.get('up_per_delivered'), 1), f(v.get('total_per_delivered'), 1)])
print(table(['SDK', 'CPU net мс/событие', 'Track p50 мкс', 'p99 мкс', 'PSS пик МБ', 'доля доставлена', 'байт/событие вверх', 'байт/событие всего с TLS'], rows))

# ---- delivery / field preservation (emulator, marker runs) ----
import subprocess
sys.path.insert(0, str(Path(__file__).resolve().parent)); import wire
def fid_rows(setname, pattern=None):
    rows = []
    for d in sorted((R / setname).iterdir()):
        if not d.is_dir() or d.name.startswith('warm'): continue
        fj = d / 'fidelity.json'
        if not fj.exists(): continue
        try: fid = json.loads(fj.read_text())
        except Exception: continue
        run = json.loads((d / 'run.json').read_text()) if (d / 'run.json').exists() else {}
        res = json.loads((d / 'result.json').read_text()) if (d / 'result.json').exists() else {}
        sdk = fid.get('sdk', d.name)
        w = None
        wp = d / 'wire.jsonl'
        if wp.exists() and wp.stat().st_size and fid.get('delivered_unique'):
            try: w = wire.summarize(str(wp), 'mortris_v8' if sdk.startswith('mortris') else sdk, fid['delivered_unique'])
            except Exception: pass
        rows.append((d.name, sdk, fid, run, res, w))
    return rows
for ds in ('puzzle', 'casual', 'midcore', 'telemetry'):
    rows = []
    for name, sdk, fid, run, res, w in fid_rows('fid'):
        if not name.startswith(ds + '_'): continue
        tracked = res.get('tracked')
        rows.append([NAMES.get(sdk, sdk) + ('' if fid.get('basis') == 'wire' else ' *расчёт по лимитам*'), f"{fid['delivered_unique']}/{fid['sent']}", f"{fid['events_fully_preserved_pct_of_sent']:.1f}", f"{fid['props_lost_pct']:.2f}", fid.get('strings_truncated', 0), fid.get('type_changed', 0) if sdk != 'adjust' else 'все → строки',
                     f"{w['per_event_up']:.1f}" if w else '—', f"{w['per_event_with_tls']:.1f}" if w else '—', run.get('settled', '—') if run else '—'])
    if rows:
        print(f'\n## Таблица B-{ds}. Доставка и сохранность полей, датасет {ds} (2000 событий, пачки по 20 за кадр, дренаж до тишины)\n')
        print(table(['SDK', 'доставлено', 'событий целиком %', 'потеряно свойств %', 'строк обрезано', 'тип изменён', 'байт/событие вверх', 'байт/событие всего с TLS', 'как закончили'], rows))

# ---- chaos ----
def cell_info(d):
    run = json.loads((d / 'run.json').read_text()) if (d / 'run.json').exists() else {}
    fid = json.loads((d / 'fidelity.json').read_text()) if (d / 'fidelity.json').exists() and (d / 'fidelity.json').stat().st_size else {}
    if fid and str(fid.get('sdk', '')).startswith('mortris') and run.get('db0') is not None and run.get('db1') is not None:
        stored = run['db1'] - run['db0']
        if stored < fid.get('delivered_unique', 0): fid = dict(fid, delivered_unique=max(stored, 0), events_fully_preserved_pct_of_sent=0.0, stale_guard=True)
    return run, fid
def wirestat(d, sdk, n):
    wp = d / 'wire.jsonl'
    if wp.exists() and wp.stat().st_size and n:
        try: return wire.summarize(str(wp), 'mortris_v8' if sdk.startswith('mortris') else sdk, n)
        except Exception: return None
if (R / 'chaos').exists():
    print('\n## Таблица C1. Принудительное завершение процесса (force-stop на 20-й секунде, 50 событий/с), затем перезапуск приложения и дренаж\n')
    rows = []
    for d in sorted((R / 'chaos').glob('kill_*')):
        run, fid = cell_info(d)
        if not fid: continue
        sdk = fid['sdk']; prog = int((d / 'progress.txt').read_text().strip() or 0) if (d / 'progress.txt').exists() else None
        got = fid['delivered_unique']
        rows.append([NAMES.get(sdk, sdk), prog, got, f"{max(prog - got, 0)}" if prog else '—', fid['duplicates'], f"{fid['props_lost_pct']:.2f}"])
    print(table(['SDK', 'принято к моменту убийства (≈, шаг 10)', 'доставлено после перезапуска', 'потеряно (≈)', 'дубликаты', 'потеряно свойств %'], rows))
    for tag, title in (('net_loss', 'Таблица C2. Обрыв 2% запросов'), ('net_bad', 'Таблица C3. Плохая сеть: задержка 400±200 мс, 128 кбит/с, 8% запросов обрываются')):
        rows = []
        for d in sorted((R / 'chaos').glob(tag + '_*')):
            run, fid = cell_info(d)
            if not fid: continue
            sdk = fid['sdk']; w = wirestat(d, sdk, fid['delivered_unique'])
            rows.append([NAMES.get(sdk, sdk), f"{fid['delivered_unique']}/{fid['sent']}", fid['duplicates'], f"{w['per_event_up']:.1f}" if w else '—', w['requests'] if w else '—', run.get('settled'), round(run.get('tail_s', 0))])
        if rows:
            print(f'\n## {title} (3000 событий, 20 за кадр)\n'); print(table(['SDK', 'доставлено', 'дубликаты', 'байт/событие вверх', 'запросов', 'как закончили', 'хвост, с'], rows))
    rows = []
    for d in sorted((R / 'chaos').glob('offline_*')):
        run, fid = cell_info(d)
        if not fid: continue
        sdk = fid['sdk']; w = wirestat(d, sdk, fid['delivered_unique'])
        rows.append([NAMES.get(sdk, sdk), f"{fid['delivered_unique']}/{fid['sent']}", fid['duplicates'], f"{w['per_event_up']:.1f}" if w else '—', run.get('settled'), round(run.get('tail_s', 0)), round(run.get('backend_back_at', 0))])
    if rows:
        print('\n## Таблица C4. Сервер недоступен всё время игры (5 минут, 10 событий/с), затем возвращается\n'); print(table(['SDK', 'доставлено после возврата', 'дубликаты', 'байт/событие вверх', 'как закончили', 'хвост до тишины, с', 'сервер вернулся на с'], rows))
if (R / 'drain').exists():
    rows = []
    for d in sorted((R / 'drain').iterdir()):
        run, fid = cell_info(d)
        if not fid: continue
        w = wirestat(d, fid['sdk'], fid['delivered_unique'])
        rows.append([NAMES.get(fid['sdk'], fid['sdk']), f"{fid['delivered_unique']}/{fid['sent']}", round(run.get('tail_s', 0)), run.get('settled'), w['requests'] if w else '—', f"{w['per_event_up']:.0f}" if w else '—'])
    if rows: print('\n## Таблица C5. Дренаж очереди Amplitude 2.40.1 (2000 событий, ждём до 7 минут тишины)\n'); print(table(['SDK', 'доставлено', 'хвост, с', 'как закончили', 'запросов', 'байт/событие вверх'], rows))
# ---- param sweeps / bursts ----
for setname, title in (('param1', 'Таблица D. Размер пачки и частота событий'), ('param2', 'Таблица E2. Всплески (эмулятор)'), ('phone_burst', 'Таблица E. Всплески на телефоне (Nothing A142)')):
    if not (R / setname).exists(): continue
    rows = []
    for d in sorted((R / setname).iterdir()):
        if not d.is_dir(): continue
        run, fid = cell_info(d)
        if not (d / 'run.json').exists(): continue
        res = json.loads((d / 'result.json').read_text()) if (d / 'result.json').exists() else {}
        sdk = None
        for k in sorted(NAMES, key=len, reverse=True):
            if d.name.endswith('_' + k): sdk = k; break
        n = res.get('tracked') or res.get('events') or 0
        delivered = (run.get('db1', 0) - run.get('db0', 0)) if run.get('db0') is not None else (run.get('final_stats', {}).get('events') or 0)
        w = wirestat(d, sdk or 'x', delivered or n)
        rows.append([d.name.rsplit('_' + (sdk or ''), 1)[0], NAMES.get(sdk, sdk), n, delivered, f"{w['per_event_up']:.1f}" if w else '—', f"{w['per_event_with_tls']:.1f}" if w else '—', w['requests'] if w else '—',
                     f"{res['track_us']['p50']:.0f}/{res['track_us']['p99']:.0f}" if res.get('track_us') else '—', f"{res['frame_work_ms']['max']:.0f}" if res.get('frame_work_ms') else '—', f"{res['mem_peak'][0]/1024:.0f}" if res.get('mem_peak') else '—', run.get('settled'), round(run.get('tail_s', 0))])
    if rows: print(f'\n## {title}\n'); print(table(['ячейка', 'SDK', 'принято', 'доставлено', 'байт/событие вверх', 'с TLS', 'запросов', 'Track p50/p99 мкс', 'макс. работа в кадре мс', 'PSS пик МБ', 'как закончили', 'хвост, с'], rows))
# ---- server ----
if (R / 'server').exists():
    rows = []
    for d in sorted((R / 'server').iterdir()):
        if not (d / 'result.json').exists(): continue
        r = json.loads((d / 'result.json').read_text()); lg = r.get('loadgen') or {}
        rows.append([d.name, r['db_events'], lg.get('requests', '—'), lg.get('wall_s', '—'), lg.get('errors', '—'), f"{r['server_cpu_us_per_event']:.0f}", f"{r['pg_cpu_us_per_event']:.0f}", f"{r['server_rss_peak_mb']:.0f}", f"{r['pg_rss_peak_mb']:.0f}"])
    print('\n## Таблица F. Нагрузка на сервер (N параллельных установок, 100-событийные пачки, реальные события holdout)\n'); print(table(['запуск', 'событий в БД', 'запросов', 'время, с', 'ошибок установок', 'CPU сервера мкс/событие', 'CPU PostgreSQL мкс/событие', 'RSS сервера МБ', 'RSS PG МБ'], rows))
if (R / 'chaos_b').exists():
    rows = []
    for d in sorted((R / 'chaos_b').glob('offline_*')):
        run, fid = cell_info(d)
        if not fid: continue
        sdk = fid['sdk']; w = wirestat(d, sdk, fid['delivered_unique'])
        rows.append([NAMES.get(sdk, sdk), f"{fid['delivered_unique']}/{fid['sent']}", fid['duplicates'], f"{w['per_event_up']:.1f}" if w else '—', run.get('settled'), round(run.get('tail_s', 0)), round(run.get('backend_back_at', 0))])
    if rows:
        print('\n## Таблица C4b. Повтор оффлайна: 3 минуты без сервера (1800 событий), затем ожидание до 10 минут тишины\n'); print(table(['SDK', 'доставлено после возврата', 'дубликаты', 'байт/событие вверх', 'как закончили', 'хвост до тишины, с', 'сервер вернулся на с'], rows))
