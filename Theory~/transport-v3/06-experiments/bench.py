"""Fixed seeds, paired workloads; all body sizes include a V3 envelope (defined in spec).
Saves machine-readable results after each profile. python bench.py
"""
import sys, time, json, platform, gzip, lzma, statistics, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'transport-v2/04-experiments'))
import wire
from gen import dataset
from alternate import dataset_alt
from codec import transform,safe_payload
import zstandard as z, brotli,pyppmd
from models import code,selfcheck

def comp(level,d=None,ldm=False):
    p=z.ZstdCompressionParameters.from_level(level,format=z.FORMAT_ZSTD1_MAGICLESS,write_content_size=False,write_dict_id=False,write_checksum=False,enable_ldm=ldm)
    return z.ZstdCompressor(compression_params=p,dict_data=d)
def samples(ds,mode=None):
    return [wire.mtb2_encode(i,transform(b,mode) if mode else b) for i,bs in ds for b in bs]
def rebatch(ds,n):
    return [(i,[ev[k:k+n] for k in range(0,len(ev),n)]) for i,bs in ds for ev in [[e for b in bs for e in b]]]
def train(xs,size=16384):return z.train_dictionary(size,xs,level=19)
def total(xs,compress):return sum(len(compress(x)) for x in xs)
def main():
    result={'environment':{'python':sys.version,'machine':platform.machine(),'platform':platform.platform(),'zstd':z.ZSTD_VERSION},'profiles':{}}
    selfcheck()
    # Separate generator; train seed 202 and test seed 101, no search over seed.
    workloads={'base':(dataset(101,installs=6),dataset(202,installs=18)),
               'rich':(dataset(101,installs=6,rich=True),dataset(202,installs=18,rich=True)),
               'alt':(dataset_alt(101),dataset_alt(202,installs=18))}
    shared=None
    for name,(test,tr) in workloads.items():
        print('START',name,flush=True);n=sum(len(b) for _,bs in test for b in bs);nb=sum(len(bs) for _,bs in test)
        xs=samples(test);ts=samples(tr);d=train(ts);d64=train(ts,65536)
        if shared is None:shared=d
        measures={};cpu={}
        def record(label,blobs,f,overhead=0):
            start=time.perf_counter();size=total(blobs,f);elapsed=time.perf_counter()-start
            measures[label]=(size+overhead*len(blobs))/n;cpu[label]=elapsed*1e6/len(blobs)
            print(name,label,round(measures[label],4),flush=True)
        v1=[wire.v1_json(i,b) for i,bs in test for b in bs]
        jtrain=[wire.v1_json(i,b) for i,bs in tr for b in bs];jd=train(jtrain)
        record('V1_gzip1',v1,lambda x:gzip.compress(x,1,mtime=0))
        record('V1_gzip6',v1,lambda x:gzip.compress(x,6,mtime=0))
        record('V1_zstd_dict16',v1,comp(19,jd).compress)
        for lvl in (3,9,19,22):record('V2_dict16_l'+str(lvl),xs,comp(lvl,d).compress,2)
        record('V2_no_dict',xs,comp(19).compress,2)
        record('V2_ood_base_dict',xs,comp(19,shared).compress,2)
        record('V2_dict64',xs,comp(19,d64).compress,2)
        record('V2_ldm',xs,comp(19,d,True).compress,2)
        for q in (5,11):record('V2_brotli'+str(q),xs,lambda x,q=q:brotli.compress(x,quality=q),2)
        record('V2_xz9',xs,lambda x:lzma.compress(x,preset=9),2)
        record('V2_ppmd8',xs,lambda x:pyppmd.compress(x,max_order=8,mem_size=4<<20),2)
        # Reversible field predictors: own trained dictionaries, same envelope budget.
        for mode in ('linear','per_type','xor','prefix','replay_hash'):
            bt=samples(test,mode);dt=train(samples(tr,mode));record(mode,bt,comp(19,dt).compress,2)
        # V3 envelope: version, kind, dict-ID, exact payload length, compressed bytes.
        # Adaptive includes literal/gzip escape; 64K selection is negotiated, dictionary transfer excluded.
        def envelope_size(raw,c):return 3+len(wire.uvarint(len(raw)))+len(c)
        def v3(ds,dc):
            sizes=[];kinds={};
            for i,bs in ds:
                for b in bs:
                    kind,raw=safe_payload(i,b);kinds[kind]=kinds.get(kind,0)+1
                    body=min((comp(19,dc).compress(raw),comp(19).compress(raw),gzip.compress(raw,6,mtime=0),raw),key=len)
                    sizes.append(envelope_size(raw,body))
            return sum(sizes)/n,kinds
        measures['V3_same_batches'],kinds=v3(test,d64)
        for count in (25,50,100,500):
            bt=rebatch(test,count);measures['V3_batch'+str(count)],_=v3(bt,d64)
            record('V2_batch'+str(count),samples(bt),comp(19,d).compress,2)
        # Replay-only extreme combines bigger batches and own trained transform dictionary.
        dt=train(samples(rebatch(tr,100),'replay_hash'),65536)
        record('extreme_replay_batch100',samples(rebatch(test,100),'replay_hash'),comp(19,dt).compress,6)
        # True PPMd history upper benchmark, not deployable body: whole-install compression.
        groups=[b''.join(wire.mtb2_encode(i,b) for b in bs) for i,bs in test]
        record('ppmd_whole_install',groups,lambda x:pyppmd.compress(x,max_order=12,mem_size=16<<20),2)
        # Context arithmetic, trained byte priors (256*contexts), actual reversible output.
        from collections import Counter
        priors={}
        for t in ts[:80]:
            prev=256
            for byte in t:
                priors.setdefault((0,prev),Counter())[byte]+=1;prev=byte
        subset=xs[:8];start=time.perf_counter();ac=[]
        for x in subset:
            c=code([x],priors);assert code([b''],priors,decode=c,lengths=[len(x)])==[x];ac.append(c)
        ac_stats={'bytes':sum(map(len,ac)),'input_bytes':sum(map(len,subset)),'zstd_bytes':total(subset,comp(19,d).compress),'batches':len(subset),'encode_and_decode_us_per_batch':(time.perf_counter()-start)*1e6/len(subset),'prior_json_bytes':len(json.dumps({str(k):dict(v) for k,v in priors.items()}))}
        # Type transition trained Markov/n-gram: cross-entropy, not a materialized wire format.
        from collections import defaultdict
        counts=[defaultdict(Counter) for _ in range(3)];names=set()
        for _,bs in tr:
            history=[]
            for e in [e for b in bs for e in b]:
                token=e['name'];names.add(token)
                for order in range(3):counts[order][tuple(history[-order:]) if order else ()][token]+=1
                history.append(token)
        import math
        bits=[0,0,0]
        for _,bs in test:
            history=[]
            for e in [e for b in bs for e in b]:
                for order in range(3):
                    c=counts[order][tuple(history[-order:]) if order else ()];bits[order]-=math.log2((c[e['name']]+1)/(sum(c.values())+len(names)+1))
                history.append(e['name'])
        result['profiles'][name]={'events':n,'batches':nb,'mean_batch':n/nb,'body_B_per_event':measures,'compress_us_per_batch':cpu,'safe_kinds':kinds,'arithmetic':ac_stats,'type_model_bits_per_event':[x/n for x in bits]}
        (ROOT/'results/bench.json').write_text(json.dumps(result,indent=2))
        (ROOT/'results'/('dict64_'+name+'.bin')).write_bytes(d64.as_bytes())
        print('DONE',name,flush=True)
if __name__=='__main__':main()
