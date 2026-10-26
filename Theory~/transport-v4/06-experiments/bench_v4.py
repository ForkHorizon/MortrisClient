"""Paired fully framed comparison; train each format at identical dictionary budget."""
import sys,json,time,hashlib,platform
from pathlib import Path
ROOT=Path(__file__).resolve().parent
import core,wire,framing,exact
from workloads import make,rebatch,drift
import zstandard as z
from bench import comp
from frame import pack as pack3
from codec import safe_payload,transform,restore

CONFIGS={
 'clean':dict(advanced=False,ef=False,float_opt=False,local=False,split_strings=False),
 'packed':dict(advanced=True,ef=True,float_opt=True,local=True,split_strings=True),
 'noef':dict(advanced=True,ef=False,float_opt=True,local=True,split_strings=True),
 'trailer':dict(advanced=True,ef=True,float_opt=True,local=True,split_strings=True,trailer=True),
 'replay':dict(advanced=True,ef=True,float_opt=True,local=True,split_strings=True,replay=True),
}
def blobs(ds,model):
    out=[]
    for inst,bs in ds:
        for batch in bs:
            if model in ('V2','V3'):raw=wire.mtb2_encode(inst,batch);tail=b''
            elif model=='V3replay':raw=wire.mtb2_encode(inst,transform(batch,'replay_hash'));tail=b''
            else:raw,tail=core.encode(inst,batch,**CONFIGS[model])
            out.append((inst,batch,raw,tail))
    return out

def measure(test,train,model,size,level=19,save=None):
    xs=blobs(test,model);ts=blobs(train,model);d=z.train_dictionary(size,[r for _,_,r,_ in ts],level=19)
    if save:(ROOT/'results'/save).write_bytes(d.as_bytes())
    n=sum(len(b) for _,b,_,_ in xs);total=rawtotal=0;start=time.perf_counter()
    for inst,b,raw,tail in xs:
        if model=='V2':f=b'\x20\x01'+comp(level,d).compress(raw)
        elif model.startswith('V3'):f=pack3(2 if model=='V3replay' else 1,raw,d,1)
        else:
            f=framing.pack(raw,tail,len(b),d,1,level)
            kind,r,t,nn=framing.unpack(f,{1:d});meta,ev=core.decode(r,t)
            assert nn==len(ev)==len(b) and exact.render(inst,ev)==exact.render(inst,b)
        total+=len(f);rawtotal+=len(raw)+len(tail)
    return {'B_per_event':total/n,'bytes':total,'raw_B_per_event':rawtotal/n,'events':n,'batches':len(xs),'elapsed_s':time.perf_counter()-start,'dict_bytes':size,'level':level}

def main():
    out={'environment':{'python':sys.version,'platform':platform.platform(),'zstd':z.ZSTD_VERSION},'frozen_seeds':{'train':202,'validation':303,'holdout':909,'independent_drift':808},'profiles':{}}
    for name in ['base','rich','alt']:
        test=make(name,101,6);train=make(name,202,18);rows={}
        for cap in [0,100,500]:
            te=rebatch(test,cap) if cap else test;tr=rebatch(train,cap) if cap else train
            for size in [16384,65536]:
                models=['V2','V3','clean','packed']
                if cap==100 and size==65536:models+=['noef','trailer','V3replay','replay']
                if cap==500 and size==65536:models+=['V3replay','replay']
                for model in models:
                    key=f'{cap or "original"}/{size}/{model}'
                    row=measure(te,tr,model,size,save=f'dict-{name}-{model}.bin' if cap==100 and size==65536 else None);rows[key]=row
                    print(name,key,round(row['B_per_event'],5),flush=True)
            out['profiles'][name]=rows;(ROOT/'results/paired-matrix.json').write_text(json.dumps(out,indent=2))
        # Validation is distinct from the old test corpus used for historical comparison.
        val=rebatch(make(name,303,3),100);tr=rebatch(train,100)
        vals={m:measure(val,tr,m,65536) for m in ['clean','packed','noef','trailer']}
        winner=min(vals,key=lambda m:vals[m]['B_per_event']);out['profiles'][name]['validation']={'rows':vals,'best':winner}
        print('VALIDATION',name,winner,flush=True)
        (ROOT/'results/paired-matrix.json').write_text(json.dumps(out,indent=2))
if __name__=='__main__':main()
