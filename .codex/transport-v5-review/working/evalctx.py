"""Evaluate MTB5 context coder against identical workloads; every frame decoded and rendered vs V1-minus-id."""
import json,time,sys,pickle,os
from common import *
import exact
import ctxcodec as cc

def train(name,cap,hash_rule=False,passes=1):
    m=cc.Model();tr=workload(name,'train202',cap if name!='drift' else 0)
    for _ in range(passes):
        for inst,bs in tr:
            for b in bs:
                cc.encode(m,inst.install_id,b,False,hash_rule)
    m.reset_batch_state();return m

def evaluate(name,test,cap,snap,stateful=False,hash_rule=False,verify=True,costs=None):
    te=workload(name,test,cap);n=tot=nb=bits=0;tenc=0.0
    for inst,bs in te:
        em=snap.clone() if stateful else None;dm=snap.clone() if stateful else None
        for b in bs:
            m=em if stateful else snap.clone()
            t0=time.perf_counter();f,nbits=cc.encode(m,inst.install_id,b,stateful,hash_rule,costs);tenc+=time.perf_counter()-t0
            if verify:
                d=dm if stateful else snap.clone()
                iid,ev=cc.decode(d,f,stateful,hash_rule)
                assert iid==inst.install_id and exact.render(inst,ev)==exact.render(inst,b),(name,test,cap)
            n+=len(b);tot+=len(f);nb+=1;bits+=nbits
    return dict(profile=name,test=test,cap=cap,stateful=stateful,hash_rule=hash_rule,events=n,batches=nb,B_per_event=tot/n,binary_decisions_per_event=bits/n,py_encode_us_per_event=tenc/n*1e6)
if __name__=='__main__':
    name=sys.argv[1];cap=int(sys.argv[2])
    snap=train(name,cap)
    print(len(snap.probs),'contexts')
    print(evaluate(name,'test101',cap,snap))
    print(evaluate(name,'test101',cap,snap,stateful=True))
