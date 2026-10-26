"""Counts events in Firebase upload bodies (protobuf, wire level). Layout assumption checked on real data: top message field 1 = Bundle (repeated); Bundle field 2 = Event (repeated)."""
import sys, os, json
def varint(b, i):
    r = 0; s = 0
    while True:
        c = b[i]; i += 1; r |= (c & 0x7f) << s; s += 7
        if not c & 0x80: return r, i
def fields(b):
    i = 0; out = []
    while i < len(b):
        k, i = varint(b, i); f, w = k >> 3, k & 7
        if w == 0: v, i = varint(b, i)
        elif w == 2: l, i = varint(b, i); v = b[i:i + l]; i += l
        elif w == 1: v = b[i:i + 8]; i += 8
        elif w == 5: v = b[i:i + 4]; i += 4
        else: raise ValueError('wire ' + str(w))
        out.append((f, w, v))
    return out
d = sys.argv[1]; tot = dict(uploads=0, events=0, gz=0, raw=0, bundles=0, names={})
for f in sorted(os.listdir(d)):
    if not f.endswith('.bin'): continue
    raw = open(os.path.join(d, f), 'rb').read(); gz = int(open(os.path.join(d, f[:-4] + '.gz.len')).read())
    try:
        top = fields(raw); bundles = [v for ff, w, v in top if ff == 1 and w == 2]
        ev = 0
        for bd in bundles:
            evs = [v for ff, w, v in fields(bd) if ff == 2 and w == 2]; ev += len(evs)
            for e in evs:
                for ff, w, v in fields(e):
                    if ff == 2 and w == 2: n = v.decode('utf8', 'replace'); tot['names'][n] = tot['names'].get(n, 0) + 1; break
    except Exception as e:
        print('parse fail', f, e); continue
    tot['uploads'] += 1; tot['events'] += ev; tot['gz'] += gz; tot['raw'] += len(raw); tot['bundles'] += len(bundles)
tot['gz_bytes_per_event'] = tot['gz'] / max(tot['events'], 1); tot['raw_bytes_per_event'] = tot['raw'] / max(tot['events'], 1)
print(json.dumps({k: v for k, v in tot.items() if k != 'names'}), dict(sorted(tot['names'].items(), key=lambda x: -x[1])[:8]))
