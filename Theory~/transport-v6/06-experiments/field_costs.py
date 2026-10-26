"""Additive PRE-compression accounting; not an entropy attribution."""
import json
from collections import defaultdict
from codec import *
from support import ROOT,make,rebatch,drift
out={}
for profile in ('base','rich','alt','drift'):
    schema=Schema(json.loads((ROOT/'results'/f'schema-{profile}.json').read_text()))
    ds=drift(1733,4,600) if profile=='drift' else rebatch(make(profile,1729,6),100)
    a=Aliases(epoch=b'fields06');cost=defaultdict(int);rawbytes=events=0
    for inst,bs in ds:
        for b in bs:
            a.register(inst.install_id,b)
            cols={}
            for e in b:
                for k,t in shape(e)[1]:
                    if t not in (REF_CTX,REF_PROP):
                        cols.setdefault((k,t),[]).append(e['properties'][k])
            props=0
            for (k,t),values in cols.items():
                size=len(enc_values(t,values));cost['properties.'+k]+=size;props+=size
            raw=encode_raw(schema,a,inst.install_id,b)
            cost['shared_shapes_context_time_sequence_and_extensions']+=len(raw)-props
            rawbytes+=len(raw);events+=len(b)
    assert sum(cost.values())==rawbytes
    out[profile]={'events':events,'raw_bytes':rawbytes,'raw_B_event':rawbytes/events,'columns':{k:{'bytes':v,'B_event':v/events} for k,v in sorted(cost.items())},'scope':'raw value payload plus shared metadata; final compression is nonadditive; no frame header/handshake'}
(ROOT/'results/field-costs.json').write_text(json.dumps(out,indent=2))
print('Raw-column accounting balances on all four holdouts')
