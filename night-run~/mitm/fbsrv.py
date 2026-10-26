"""TLS sink for Firebase Analytics uploads (emulator-only, hosts file points app-measurement.com here). Logs request sizes; replies 200 empty/204."""
import http.server, ssl, sys, json, time, gzip
LOG = sys.argv[2]
class H(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def do_POST(self):
        n = int(self.headers.get('content-length', 0)); body = self.rfile.read(n) if n else b''
        if self.headers.get('transfer-encoding', '') == 'chunked':
            body = b''
            while True:
                sz = int(self.rfile.readline().strip() or b'0', 16)
                if sz == 0: self.rfile.readline(); break
                body += self.rfile.read(sz); self.rfile.readline()
        raw = body
        if self.headers.get('content-encoding', '') == 'gzip':
            try: raw = gzip.decompress(body)
            except Exception: pass
        rec = dict(t=time.time(), host=self.headers.get('Host', ''), method=self.command, path=self.path, hdr=sum(len(k) + len(v) + 4 for k, v in self.headers.items()), body=len(body), decoded=len(raw), enc=self.headers.get('content-encoding', ''), ctype=self.headers.get('content-type', ''))
        open(LOG, 'a').write(json.dumps(rec) + '\n')
        if not self.path.startswith('/a') and self.command == 'POST' and 'installations' not in self.path:
            import os
            d = LOG + '.other'; os.makedirs(d, exist_ok=True); n = len(os.listdir(d)); open(f'{d}/{n:05d}.bin', 'wb').write(raw); open(f'{d}/{n:05d}.meta', 'w').write(json.dumps(rec))
        if self.path.startswith('/a'):
            import os
            d = LOG + '.bodies'; os.makedirs(d, exist_ok=True); n = len(os.listdir(d)); open(f'{d}/{n:04d}.bin', 'wb').write(raw); open(f'{d}/{n:04d}.gz.len', 'w').write(str(len(body)))
        if '/installations' in self.path:
            try: fid = json.loads(raw).get('fid', 'cAAAAAAAAAAAAAAAAAAAAA')
            except Exception: fid = 'cAAAAAAAAAAAAAAAAAAAAA'
            out = json.dumps({'name': 'projects/bench-proj/installations/' + fid, 'fid': fid, 'refreshToken': '1_fakeRefreshToken', 'authToken': {'token': 'fake.auth.token', 'expiresIn': '604800s'}}).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(out))); self.end_headers(); self.wfile.write(out); return
        if self.path.startswith('/a'): self.send_response(204); self.send_header('Content-Length', '0'); self.end_headers(); return
        out = b'{"success":true}'
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(out))); self.end_headers(); self.wfile.write(out)
    do_GET = do_POST
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(('0.0.0.0', int(sys.argv[1])), H)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain('srv.crt', 'srv.key'); srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
srv.serve_forever()
