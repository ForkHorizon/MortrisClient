"""On-wire totals with the user's own network model (transport-v3 network.py wire_total, HPACK never-indexed,
ACK 2 B, warm connection, setup 0 / 750 B). Same batches for V4 and MTB5."""
import json,uuid
from common import *
import core,framing,exact
import zstandard as z
from network import cut,hpack_size,wire_total
from evalctx import train
import ctxcodec as cc
HP=hpack_size()[-1]
d4=z.ZstdCompressionDict((EXP/'results/dict-base-trailer.bin').read_bytes())
snap=train('base',100)
def bodies(inst,chunks):
    out={'V4':[],'MTB5_stateless':[],'MTB5_stateful':[]};sm=snap.clone()
    for b in chunks:
        r,t=core.encode(inst,b,trailer=True);out['V4'].append(len(framing.pack(r,t,len(b),d4,1,19)))
        out['MTB5_stateless'].append(len(cc.encode(snap.clone(),inst.install_id,b)[0]))
        out['MTB5_stateful'].append(len(cc.encode(sm,inst.install_id,b,True)[0]))
    return out
def totals(chunks,bod,nev):
    res={}
    for model,bs in bod.items():
        r={'body_B_per_event':sum(bs)/nev}
        for proto in ('h1','h2','h3'):
            for setup in (0,750):
                r[f'{proto}_setup{setup}']=sum(wire_total(body,2,len(b),proto,setup,0,HP)*len(b) for body,b in zip(bs,chunks))/nev
        res[model]=r
    return res
out={'hpack_bytes':HP,'patterns':{}}
inst,bs=make('base',101,1)[0];original=[e for b in bs for e in b][:900]
for pattern in ['dense_1s','sparse_45s','short_8','offline_900']:
    events=[]
    for i,e in enumerate(original):
        t=1790000000000+i*(45000 if pattern=='sparse_45s' else 1000)
        if pattern=='short_8':t=1790000000000+(i//8)*600000+(i%8)*1000
        events.append({**e,'ts':t,'session_id':original[0]['session_id'] if pattern!='short_8' else str(uuid.UUID(int=i//8+1))})
    chunks=[events[k:k+100] for k in range(0,len(events),100)] if pattern=='offline_900' else cut(events,100,30000)
    out['patterns'][pattern]={'batches':len(chunks),**totals(chunks,bodies(inst,chunks),len(events))}
    print(pattern,json.dumps(out['patterns'][pattern]),flush=True)
# test101 at original uploader cadence (all installs)
te=workload('base','test101',0);agg={};n=0
for inst,chunks in te:
    t=totals(chunks,bodies(inst,chunks),1)
    for m,r in t.items():
        for k,v in r.items():agg.setdefault(m,{}).setdefault(k,0);agg[m][k]+=v
    n+=sum(len(b) for b in chunks)
out['test101_original_cadence']={m:{k:v/n for k,v in r.items()} for m,r in agg.items()}
print(json.dumps(out['test101_original_cadence']))
json.dump(out,open('results/wire.json','w'),indent=1)
