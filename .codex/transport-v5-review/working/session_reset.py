"""Stateful only within an app session: model+previous values reset to the shipped prior whenever a batch
starts a new session (no model persistence on disk across launches)."""
import json,time
from evalctx import *
import ctxcodec as cc
rows=[]
for name,cap in [('base',0),('base',100),('rich',0),('rich',100),('alt',100),('drift',0)]:
    snap=train(name,cap);te=workload(name,'hold909' if name=='drift' else 'test101',cap);n=tot=0;resets=0
    for inst,bs in te:
        em=dm=None;last_sid=None
        for b in bs:
            if em is None or b[0]['session_id']!=last_sid:em=snap.clone();dm=snap.clone();resets+=1;stateless_first=True
            f,_=cc.encode(em,inst.install_id,b,True);iid,ev=cc.decode(dm,f,True)
            assert exact.render(inst,ev)==exact.render(inst,b)
            n+=len(b);tot+=len(f);last_sid=b[-1]['session_id']
    r=dict(profile=name,cap=cap,mode='stateful_reset_per_session',B_per_event=tot/n,events=n,resets=resets);print(r,flush=True);rows.append(r)
json.dump(rows,open('results/mtb5_session_reset.json','w'),indent=1)
