#!/usr/bin/env python3
"""Wire accounting for one run from collector2's JSONL. Cleartext socket bytes (HTTP headers + bodies, both directions) are measured; TLS is added by a model:
per connection one full handshake (client CLIENT_HS bytes, server bytes measured against the vendor's production host, see tls_handshake_hosts.json) and 22 B per TLS record
(<= 16384 B of plaintext each) in both directions, plus 24 B for close_notify. TLS1.3, no session resumption (conservative for every vendor equally)."""
import json, sys
CLIENT_HS = 700   # Android Conscrypt ClientHello (~520) + client Finished/CCS (~80) + TCP-level none; the host-side python client is larger (post-quantum key share) so it is not used for this side
SERVER_HS = {'amplitude': 4520, 'amplitude_kotlin': 4520, 'ga': 2523, 'firebase': 4473, 'facebook': 4536, 'adjust': 5186, 'mixpanel': 4161, 'hyperkit_core': 3000, 'hyperkit_ctx': 3000, 'mortris_v8': 3000, 'mortris_v7': 3000, 'mortris_v1': 3000}
def records(n): return -(-n // 16384) if n else 0
def summarize(path, sdk, events):
    reqs = []; closed = set(); conns = set()
    for l in open(path):
        r = json.loads(l)
        if r.get('closed'): closed.add(r['conn']); continue
        if r['path'] == '/__stats': continue
        reqs.append(r); conns.add(r['conn'])
    up_h = sum(r['req_header_bytes'] for r in reqs); up_b = sum(r['req_body_bytes'] for r in reqs)
    dn_h = sum(r['resp_header_bytes'] for r in reqs); dn_b = sum(r['resp_body_bytes'] for r in reqs)
    c = len(conns)
    tls_up = c * CLIENT_HS + sum(records(r['req_header_bytes'] + r['req_body_bytes']) * 22 for r in reqs) + c * 24
    tls_dn = c * SERVER_HS.get(sdk, 3000) + sum(records(r['resp_header_bytes'] + r['resp_body_bytes']) * 22 for r in reqs) + c * 24
    clear = up_h + up_b + dn_h + dn_b; tls = tls_up + tls_dn
    d = dict(requests=len(reqs), connections=c, up_header=up_h, up_body=up_b, down_header=dn_h, down_body=dn_b, cleartext_total=clear, tls_model=tls, with_tls=clear + tls)
    if events: d.update(per_event_body=up_b / events, per_event_up=(up_h + up_b) / events, per_event_cleartext=clear / events, per_event_with_tls=(clear + tls) / events)
    return d
if __name__ == '__main__': print(json.dumps(summarize(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 0), indent=1))
