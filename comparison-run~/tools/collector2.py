#!/usr/bin/env python3
"""Cleartext wire meter, one process per run. Counts what crosses the socket per HTTP request: request headers, request body (as sent, i.e. compressed),
response headers + body. Two modes, same JSONL record format:
  mock   (default): answers the way the competitor backends do enough for the SDK to keep sending; parses events out of the bodies.
  proxy  (--upstream HOST:PORT): forwards to the real Mortris server and records the same fields (events = -1: the server database is the delivery truth).
Usage: collector2.py PORT OUT.jsonl [--upstream H:P] [--dump DIR] [--stats-port N]
Also serves GET /__stats on the same port: {"events":N,"requests":N,"bytes_in":N,"last_activity_age_s":S,"connections":N} so the driver can decide when delivery settled."""
import asyncio, base64, collections, gzip, json, os, sys, time, urllib.parse, zlib
args = sys.argv[1:]; PORT = int(args[0]); OUT = args[1]; UP = None; DUMP = None
if '--upstream' in args: UP = args[args.index('--upstream') + 1]
if '--dump' in args: DUMP = args[args.index('--dump') + 1]; os.makedirs(DUMP, exist_ok=True)
import random
def opt(name, default=0.0): return float(args[args.index(name) + 1]) if name in args else default
DELAY, JITTER, DROP, BW = opt('--delay-ms'), opt('--jitter-ms'), opt('--drop'), opt('--bw-kbps')
T0 = time.time(); STATS = dict(events=0, requests=0, bytes_in=0, bytes_out=0, connections=0, last=time.time()); KINDS = collections.Counter(); SEEN = set()
open(OUT, 'w').close(); DUMPN = [0]

def decode_body(h, body):
    ce = h.get('content-encoding', '')
    try:
        if ce == 'gzip' and body: return gzip.decompress(body)
        if ce == 'deflate' and body: return zlib.decompress(body)
    except Exception: pass
    return body

def parse_events(path, h, body):
    raw = decode_body(h, body); n = 0
    try:
        p = path.split('?')[0]
        if p.startswith('/ampk'):
            v = json.loads(raw); ev = v.get('events', []); n = len(ev)
            for e in ev: KINDS[e.get('event_type', '?')] += 1
            if DUMP: dump(ev)
        elif p.startswith('/amp'):
            q = urllib.parse.parse_qs(raw.decode('utf-8')); ev = json.loads(q['e'][0]) if 'e' in q else []; n = len(ev)
            for e in ev: KINDS[e.get('event_type', '?')] += 1
            if DUMP: dump(ev)
        elif p.startswith('/ga') and p.endswith('/events'):
            v = json.loads(raw); v = v if isinstance(v, list) else [v]; n = len(v)
            for e in v: KINDS[e.get('category', '?')] += 1
            if DUMP: dump(v)
        elif p.startswith('/hk/events'):
            v = json.loads(raw); v = v if isinstance(v, list) else [v]; n = len(v)
            for e in v: KINDS['hk'] += 1
            if DUMP: dump(v)
        elif p.startswith('/mp/track') or p.startswith('/mp/engage'):
            q = urllib.parse.parse_qs(raw.decode('utf-8')); d = q.get('data', [''])[0]
            v = json.loads(base64.b64decode(d + '=' * (-len(d) % 4))); v = v if isinstance(v, list) else [v]; n = len(v)
            for e in v: KINDS[e.get('event', '?')] += 1
            if DUMP: dump(v)
    except Exception as e:
        return -1, len(raw)
    return n, len(raw)

def dump(ev):
    with open(os.path.join(DUMP, 'events.jsonl'), 'a') as f:
        for e in ev: f.write(json.dumps(e) + '\n')

async def read_head(r):
    head = await r.readuntil(b'\r\n\r\n'); lines = head.decode('latin1').split('\r\n'); h = {}
    for l in lines[1:]:
        if ':' in l: k, v = l.split(':', 1); h[k.strip().lower()] = v.strip()
    return head, lines[0], h

async def read_body(r, h, raw_out=None):
    """Returns (decoded-from-chunking body, bytes on the wire for the body incl. chunk framing)."""
    if h.get('transfer-encoding', '').lower() == 'chunked':
        body = b''; wire = b''
        while True:
            line = await r.readline(); wire += line; sz = int(line.strip().split(b';')[0] or b'0', 16)
            if sz == 0:
                while True:
                    t = await r.readline(); wire += t
                    if t in (b'\r\n', b'\n', b''): break
                break
            chunk = await r.readexactly(sz); crlf = await r.readexactly(2); body += chunk; wire += chunk + crlf
        return body, wire
    n = int(h.get('content-length', 0)); body = await r.readexactly(n) if n else b''
    return body, body

CONN = [0]
async def handle(r, w):
    CONN[0] += 1; cid = CONN[0]; STATS['connections'] += 1; first = True; up_r = up_w = None
    try:
        while True:
            head, line, h = await read_head(r); method, path, _ = line.split(' ', 2)
            body, wire_body = await read_body(r, h); STATS['last'] = time.time()
            if path != '/__stats':
                if DROP and random.random() < DROP: w.close(); return  # the connection dies with the request unanswered
                lag = (DELAY + random.uniform(0, JITTER)) / 1000 + ((len(head) + len(wire_body)) * 8 / (BW * 1000) if BW else 0)
                if lag: await asyncio.sleep(lag)
            if path == '/__stats':
                out = json.dumps(dict(STATS, last_activity_age_s=round(time.time() - STATS['last'], 2), kinds=dict(KINDS))).encode()
                w.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(out)).encode() + b'\r\n\r\n' + out); await w.drain(); continue
            resp_h = resp_b = 0; status = 0; nev = -1; dec = len(decode_body(h, body)); err = ''
            if UP:
                if up_w is None:
                    uh, up = UP.split(':'); up_r, up_w = await asyncio.open_connection(uh, int(up))
                up_w.write(head + wire_body); await up_w.drain()
                rhead, rline, rh = await read_head(up_r); rbody, rwire = await read_body(up_r, rh)
                status = int(rline.split(' ')[1]); resp_h = len(rhead); resp_b = len(rwire)
                if DUMP and path.startswith('/v3/'):
                    with open(os.path.join(DUMP, 'responses.jsonl'), 'a') as df: df.write(json.dumps(dict(path=path, status=status, req_body=len(wire_body), body=rbody.decode('utf-8', 'replace')[:2000])) + '\n')
                w.write(rhead + rwire); await w.drain()
                if rh.get('connection', '').lower() == 'close': up_w.close(); up_w = None
            else:
                if '/init' in path or 'remote_configs' in path: resp = json.dumps({'enabled': True, 'server_ts': int(time.time()), 'configs': [], 'status': 'ok'}).encode(); ctype = 'application/json'
                elif path.startswith('/amp') and not path.startswith('/ampk'): resp = b'success'; ctype = 'text/plain'
                elif path.startswith('/ampk'): resp = b'{"code":200,"server_upload_time":%d,"payload_size_bytes":0,"events_ingested":0}' % int(time.time() * 1000); ctype = 'application/json'
                elif path.startswith('/mp'): resp = b'1'; ctype = 'text/plain'
                else: resp = b'{}'; ctype = 'application/json'
                out = b'HTTP/1.1 200 OK\r\nContent-Type: ' + ctype.encode() + b'\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\n\r\n' + resp
                w.write(out); await w.drain(); status = 200; resp_h = out.index(b'\r\n\r\n') + 4; resp_b = len(resp)
                nev, dec = parse_events(path, h, body)
                if nev > 0: STATS['events'] += nev
            STATS['requests'] += 1; STATS['bytes_in'] += len(head) + len(wire_body); STATS['bytes_out'] += resp_h + resp_b
            rec = dict(t=round(time.time() - T0, 3), conn=cid, new_connection=first, method=method, path=path.split('?')[0], req_header_bytes=len(head), req_body_bytes=len(wire_body),
                       resp_header_bytes=resp_h, resp_body_bytes=resp_b, status=status, content_encoding=h.get('content-encoding', ''), decoded_body_bytes=dec, events=nev, user_agent=h.get('user-agent', ''))
            first = False
            with open(OUT, 'a') as f: f.write(json.dumps(rec) + '\n')
    except (asyncio.IncompleteReadError, ConnectionResetError, asyncio.LimitOverrunError, BrokenPipeError):
        pass
    finally:
        try:
            with open(OUT, 'a') as f: f.write(json.dumps(dict(t=round(time.time() - T0, 3), conn=cid, closed=True)) + '\n')
        except Exception: pass
        w.close()
        if up_w: up_w.close()

async def main():
    s = await asyncio.start_server(handle, '0.0.0.0', PORT, limit=1 << 26)
    async with s: await s.serve_forever()
asyncio.run(main())
