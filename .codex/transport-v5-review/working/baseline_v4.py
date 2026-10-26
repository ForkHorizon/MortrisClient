"""Reproduce V4 'trailer' (chosen model) numbers with the user's own code: own dict64 trained on train202, level19."""
import json,time,sys
from common import *
import core,framing,exact
import zstandard as z
from bench_v4 import CONFIGS
def run(name,test,cap,level=19,dsize=65536):
    tr=workload(name,'train202',cap if name!='drift' else 0); te=workload(name,test,cap)
    d=z.train_dictionary(dsize,[core.encode(i,b,**CONFIGS['trailer'])[0] for i,bs in tr for b in bs],level=19)
    ctx=framing.compressor(level,d)
    n=tot=raw=0;t_enc=0.0;nb=0
    for inst,bs in te:
        for b in bs:
            t0=time.perf_counter();r,t=core.encode(inst,b,**CONFIGS['trailer']);f=framing.pack(r,t,len(b),d,1,level,context=ctx);t_enc+=time.perf_counter()-t0
            k,rr,tt,nn=framing.unpack(f,{1:d});_,ev=core.decode(rr,tt);assert exact.render(inst,ev)==exact.render(inst,b)
            n+=len(b);tot+=len(f);raw+=len(r)+len(t);nb+=1
    v1=sum(len(exact.render(i,b)) for i,bs in te for b in bs)
    return dict(profile=name,test=test,cap=cap,events=n,batches=nb,B_per_event=tot/n,raw_B_per_event=raw/n,v1_json_B_per_event=v1/n,py_encode_us_per_event=t_enc/n*1e6)
if __name__=='__main__':
    out=[]
    for name in ['base','rich','alt']:
        for test,cap in [('test101',0),('test101',100),('test101',500),('hold909',100)]:
            r=run(name,test,cap);print(r,flush=True);out.append(r)
    r=run('drift','hold909',0);print(r,flush=True);out.append(r)
    json.dump(out,open('results/baseline_v4.json','w'),indent=1)
