#!/usr/bin/env python3
"""Exact TLS handshake bytes (client->server, server->client) against the real production hosts of each vendor: full handshake and a resumed one (session ticket),
counted on the record layer via MemoryBIO. Usage: tls_handshake.py HOST[:PORT]... > json. Only the TLS handshake is performed, no HTTP request."""
import json, socket, ssl, sys
def one(host, port, session=None):
    ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    inb, outb = ssl.MemoryBIO(), ssl.MemoryBIO(); obj = ctx.wrap_bio(inb, outb, server_hostname=host, session=session)
    s = socket.create_connection((host, port), timeout=10); tx = rx = 0
    while True:
        try: obj.do_handshake(); break
        except ssl.SSLWantReadError: pass
        d = outb.read()
        if d: s.sendall(d); tx += len(d)
        r = s.recv(65536)
        if not r: raise RuntimeError('closed')
        inb.write(r); rx += len(r)
    d = outb.read()
    if d: s.sendall(d); tx += len(d)
    # TLS1.3 session tickets arrive after the handshake: read what is already there
    s.settimeout(0.7)
    try:
        r = s.recv(65536); inb.write(r); rx += len(r)
        try: obj.read(1)
        except ssl.SSLWantReadError: pass
    except Exception: pass
    out = dict(version=obj.version(), cipher=obj.cipher()[0], client_bytes=tx, server_bytes=rx, resumed=obj.session_reused)
    sess = obj.session; s.close(); return out, sess
res = {}
for h in sys.argv[1:]:
    host, _, port = h.partition(':'); port = int(port or 443)
    try:
        full, sess = one(host, port); res[host] = dict(full=full)
        try: res[host]['resumed'] = one(host, port, sess)[0]
        except Exception as e: res[host]['resumed'] = str(e)
    except Exception as e: res[host] = dict(error=str(e))
print(json.dumps(res, indent=1))
