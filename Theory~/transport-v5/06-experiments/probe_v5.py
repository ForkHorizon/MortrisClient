import json,time,sys
from pathlib import Path
from support import make,rebatch,drift
from model import Model
from context_codec import Coder,code_batch
from frame_v5 import encode,decode,render
ROOT=Path(__file__).resolve().parent

def train(name,bits=14):
    ds=drift(202,12,600) if name=='drift' else rebatch(make(name,202,18),100)
    m=Model(bits)
    for inst,bs in ds:
        for b in bs:
            m.reset_batch_state();m.last[('install',)]=inst.install_id
            c=Coder(m,True);code_batch(c,inst.install_id,b,True)
    m.reset_batch_state();return m

def evaluate(prior,ds):
    total=n=nb=0
    for inst,bs in ds:
        for b in bs:
            f,m=encode(prior,inst.install_id,b);source,d=decode(prior,f);assert source==render(inst.install_id,b)
            assert m.snapshot(True)==d.snapshot(True)
            n+=len(b);nb+=1;total+=len(f)
    return {'events':n,'batches':nb,'bytes':total,'B_per_event':total/n}
if __name__=='__main__':
    p=sys.argv[1];prior=train(p,14);(ROOT/'results'/f'prior14-{p}.bin').write_bytes(prior.snapshot());(ROOT/'results'/f'prior14-{p}.zlib').write_bytes(prior.artifact())
    ds=drift(808,4,600) if p=='drift' else rebatch(make(p,101,6),100)
    row={'profile':p,'table_bytes':len(prior.probs)*2,'raw_prior_bytes':len(prior.snapshot()),'compressed_prior_bytes':len(prior.artifact()),'body':evaluate(prior,ds)}
    print(json.dumps(row),flush=True);(ROOT/'results'/f'probe-{p}.json').write_text(json.dumps(row,indent=2))
