"""Same test/train boundaries and complete frames; fresh heldout seeds are fixed in JSON."""
import json,time,statistics,zlib,tracemalloc,sys
from pathlib import Path
import zstandard as z
from support import make,rebatch,drift,core,wire,exact
from model import Model,context_hash
from frame_v5 import encode,decode,render
from probe_v5 import evaluate
from framing import compressor,pack
ROOT=Path(__file__).resolve().parent

def size_v4(ds,d):
    total=n=0
    for inst,bs in ds:
        for b in bs:
            raw,tail=core.encode(inst,b,trailer=True);total+=len(pack(raw,tail,len(b),d,1,19));n+=len(b)
    return total/n

def stateful(prior,ds,reset_session=False):
    total=n=nb=resets=0
    for inst,bs in ds:
        em=dm=None;last_sid=None
        for b in bs:
            if reset_session and b[0]['session_id']!=last_sid:em=dm=None;resets+=1
            f,next_em=encode(prior,inst.install_id,b,base=em);source,next_dm=decode(prior,f,base=dm)
            assert source==render(inst.install_id,b) and next_em.state_id()==next_dm.state_id()
            # Simulated full durable ACK; no advancement before both succeeded.
            em=next_em;dm=next_dm;last_sid=b[-1]['session_id'];total+=len(f);n+=len(b);nb+=1
    return {'B_per_event':total/n,'bytes':total,'events':n,'batches':nb,'session_resets':resets,'condition':'ideal hit, full ACK for each batch'}

def main(name):
    prior=Model.restore((ROOT/'results'/f'prior14-{name}.bin').read_bytes())
    train=drift(202,12,600) if name=='drift' else rebatch(make(name,202,18),100)
    d=z.train_dictionary(65536,[core.encode(i,b,trailer=True)[0] for i,bs in train for b in bs],level=19)
    rows={};out={'profile':name,'prior_raw_bytes':len(prior.snapshot()),'prior_zlib_bytes':len(prior.artifact()),'probability_table_bytes':len(prior.probs)*2,'v4_dictionary_raw_bytes':65536,'v4_dictionary_zlib_bytes':len(zlib.compress(d.as_bytes(),9)),'tables':len(prior.tables),'table_entries':prior.table_entries,'ema_entries':len(prior.ema),'rows':rows}
    cases=[('historical',101,6),('validation',303,3),('fresh_holdout',1729,6)] if name!='drift' else [('historical',808,4),('fresh_holdout',1733,4)]
    for label,seed,n in cases:
        ds=drift(seed,4,600) if name=='drift' else rebatch(make(name,seed,n),100)
        row={'seed':seed,'stateless':evaluate(prior,ds),'stateful_ideal':stateful(prior,ds),'stateful_session_reset':stateful(prior,ds,True),'V4_B_per_event':size_v4(ds,d)};rows[label]=row
        print(name,label,row,flush=True);(ROOT/'results'/f'bench-{name}.json').write_text(json.dumps(out,indent=2))
    if name!='drift':
        ds=rebatch(make(name,1729,6),100,session=True,deadline=30000)
        rows['fresh_session_deadline30s']={'stateless':evaluate(prior,ds),'V4_B_per_event':size_v4(ds,d),'stateful_ideal':stateful(prior,ds)}
    # Python actual full pipeline and model allocations; no attribution to C#/ARM.
    ds=drift(1733,4,600) if name=='drift' else rebatch(make(name,1729,6),100)
    samples=[(i,b) for i,bs in ds for b in bs][:12];times=[];peaks=[]
    context_hash.cache_clear()
    for inst,b in samples:
        start=time.perf_counter_ns();f,m=encode(prior,inst.install_id,b);source,dummy=decode(prior,f);assert source==render(inst.install_id,b);times.append((time.perf_counter_ns()-start)/1e6)
    for inst,b in samples[:3]:
        tracemalloc.start();f,m=encode(prior,inst.install_id,b);source,dummy=decode(prior,f);_,peak=tracemalloc.get_traced_memory();tracemalloc.stop();peaks.append(peak)
    out['python_pipeline']={'sample_batches':len(times),'p50_ms':statistics.median(times),'p95_ms':sorted(times)[int(.95*(len(times)-1))],'tracemalloc_peak_warm_cache_bytes':max(peaks),'cache':str(context_hash.cache_info()),'not_ARM_or_CSharp':True}
    (ROOT/'results'/f'bench-{name}.json').write_text(json.dumps(out,indent=2))
if __name__=='__main__':main(sys.argv[1])
