"""Cleartext localhost collector. Counts bytes at the TCP socket (request: headers+body, response: headers+body).
No TLS, no DNS: those are NOT in these numbers. Usage: collector.py PORT OUT.jsonl"""
import asyncio, gzip, json, os, sys, time, urllib.parse

OUT = None; T0 = time.time(); CATS = __import__('collections').Counter(); SAMPLED = set()

def keep_sample(path, events):
    # first body per endpoint kept for payload-composition evidence (synthetic data only)
    k = path.split('?')[0].split('/')[1]
    for e in events:
        c = e.get('category') or e.get('event_type', '?'); kk = k + '-' + str(c)
        if kk not in SAMPLED and (c in ('design', 'user', 'session_end') or k == 'amp'):
            SAMPLED.add(kk); open(OUT + '.sample-' + kk + '.json', 'w').write(json.dumps([e], indent=1)); 
            if k == 'amp': return

def dump_full(events):
    if os.environ.get('DUMP_FULL'):
        with open(OUT + '.events.jsonl', 'a') as f:
            for e in events: f.write(json.dumps(e) + '\n')

def parse_events(path, headers, body):
    ce = headers.get('content-encoding', '')
    raw = gzip.decompress(body) if ce == 'gzip' and body else body
    try:
        if path.startswith('/amp'):
            q = urllib.parse.parse_qs(raw.decode('utf-8'))
            ev = json.loads(q['e'][0]) if 'e' in q else []
            CATS.update(e.get('event_type', '?') for e in ev); dump_full(ev); keep_sample(path, ev); return len(ev), len(raw)
        if '/events' in path:
            v = json.loads(raw); v = v if isinstance(v, list) else [v]
            CATS.update(e.get('category', '?') for e in v); dump_full(v); keep_sample(path, v); return len(v), len(raw)
    except Exception as e:
        return -1, len(raw)
    return 0, len(raw)

async def handle(r, w):
    conn_bytes_in = conn_bytes_out = 0; first = True
    try:
        while True:
            head = await r.readuntil(b'\r\n\r\n')
            lines = head.decode('latin1').split('\r\n'); method, path, _ = lines[0].split(' ', 2)
            h = {k.strip().lower(): v.strip() for k, v in (l.split(':', 1) for l in lines[1:] if ':' in l)}
            if h.get('transfer-encoding') == 'chunked':
                body = b''
                while True:
                    sz = int((await r.readline()).strip(), 16)
                    if sz == 0: await r.readline(); break
                    body += await r.readexactly(sz); await r.readline()
                wire_body = len(body)  # chunk framing overhead not counted (documented limitation)
            else:
                n = int(h.get('content-length', 0)); body = await r.readexactly(n) if n else b''; wire_body = n
            if '/init' in path: resp = json.dumps({'enabled': True, 'server_ts': int(time.time()), 'configs': []}).encode(); ctype = 'application/json'
            else: resp = b'success' if path.startswith('/amp') else b'{}'; ctype = 'text/plain' if path.startswith('/amp') else 'application/json'
            out = b'HTTP/1.1 200 OK\r\nContent-Type: ' + ctype.encode() + b'\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\n\r\n' + resp
            w.write(out); await w.drain()
            nev, dec = parse_events(path, h, body)
            rec = dict(t=round(time.time() - T0, 3), method=method, path=path, req_header_bytes=len(head), req_body_bytes=wire_body, resp_bytes=len(out),
                       content_encoding=h.get('content-encoding', ''), decoded_body_bytes=dec, events=nev, cats=dict(CATS), new_connection=first, user_agent=h.get('user-agent', ''))
            first = False
            with open(OUT, 'a') as f: f.write(json.dumps(rec) + '\n')
    except (asyncio.IncompleteReadError, ConnectionResetError, asyncio.LimitOverrunError):
        pass
    finally:
        w.close()

async def main():
    global OUT; port, OUT = int(sys.argv[1]), sys.argv[2]; open(OUT, 'w').close()
    s = await asyncio.start_server(handle, '0.0.0.0', port)
    async with s:
        await s.serve_forever()
asyncio.run(main())
