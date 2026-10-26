#!/usr/bin/env python3
"""TLS meter for the profiling build: terminates TLS with a self-made certificate, forwards the decrypted HTTP to an upstream (collector2 in front of the Mortris server), and
records for EVERY TLS connection what really crossed the wire: raw bytes each way, how many of them belong to the handshake (everything before the first application byte,
session tickets included), whether the session was resumed, plaintext bytes each way and the TLS version and cipher. One JSON line per closed connection.
Usage: tlsmeter.py PORT UPSTREAM_HOST:PORT OUT.jsonl      (the profiling APK accepts any certificate; the normal SDK does not)"""
import asyncio, json, os, ssl, subprocess, sys, time
PORT, UPSTREAM, OUT = int(sys.argv[1]), sys.argv[2], sys.argv[3]
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'work', 'tls'); os.makedirs(D, exist_ok=True)
CERT, KEY = os.path.join(D, 'cert.pem'), os.path.join(D, 'key.pem')
if not os.path.exists(CERT):
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes', '-keyout', KEY, '-out', CERT, '-subj', '/CN=localhost', '-days', '30'], check=True, capture_output=True)
CTX = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); CTX.load_cert_chain(CERT, KEY); CTX.minimum_version = ssl.TLSVersion.TLSv1_2
open(OUT, 'w').close(); T0 = time.time(); N = [0]

async def handle(reader, writer):
    N[0] += 1; cid = N[0]; uh, up = UPSTREAM.split(':'); u_reader, u_writer = await asyncio.open_connection(uh, int(up))
    incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO(); sslobj = CTX.wrap_bio(incoming, outgoing, server_side=True)
    st = dict(rx=0, tx=0, hs_rx=None, hs_tx=None, plain_in=0, plain_out=0, hs=False, app=False); t_open = time.time() - T0

    async def flush():
        data = outgoing.read()
        if data: writer.write(data); st['tx'] += len(data); await writer.drain()

    async def from_upstream():
        try:
            while True:
                data = await u_reader.read(65536)
                if not data: break
                st['plain_out'] += len(data); sslobj.write(data); await flush()
        except Exception: pass

    pump = asyncio.ensure_future(from_upstream())
    try:
        while True:
            raw = await reader.read(65536)
            if not raw: break
            st['rx'] += len(raw); incoming.write(raw)
            while True:
                try:
                    if not st['hs']: sslobj.do_handshake(); st['hs'] = True
                    chunk = sslobj.read(65536)
                except ssl.SSLWantReadError: break
                except ssl.SSLZeroReturnError: raise EOFError
                if not chunk: break
                if not st['app']: st['app'] = True; await flush(); st['hs_rx'], st['hs_tx'] = st['rx'] - len(raw) + 0, st['tx']   # bytes before the first application data
                st['plain_in'] += len(chunk); u_writer.write(chunk); await u_writer.drain()
            await flush()
    except (EOFError, ConnectionError, ssl.SSLError, asyncio.IncompleteReadError):
        pass
    finally:
        pump.cancel()
        try: await flush()
        except Exception: pass
        rec = dict(t=round(t_open, 3), conn=cid, raw_in=st['rx'], raw_out=st['tx'], handshake_in=st['hs_rx'] if st['hs_rx'] is not None else st['rx'], handshake_out=st['hs_tx'] if st['hs_tx'] is not None else st['tx'],
                   plain_in=st['plain_in'], plain_out=st['plain_out'], resumed=bool(sslobj.session_reused) if st['hs'] else None,
                   version=sslobj.version() if st['hs'] else None, cipher=(sslobj.cipher() or [None])[0] if st['hs'] else None, duration_s=round(time.time() - T0 - t_open, 3))
        with open(OUT, 'a') as f: f.write(json.dumps(rec) + '\n')
        for w in (writer, u_writer):
            try: w.close()
            except Exception: pass

async def main():
    server = await asyncio.start_server(handle, '0.0.0.0', PORT)
    async with server: await server.serve_forever()
asyncio.run(main())
