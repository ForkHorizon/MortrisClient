"""Follow-up tests: field/type contextual arithmetic, column encodings, dictionary
specialization, long history with bounded loss/resync budget. python further.py
"""
import sys,json,math,time,struct
from pathlib import Path
from collections import Counter,defaultdict
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'transport-v2/04-experiments'))
import wire
from gen import dataset
from alternate import dataset_alt
from codec import transform
from models import code
from bench import comp,train,samples
import zstandard as z

def fields(batch):
    # Stream identities transmitted in schema directory in a full codec. This
    # experiment measures value stage only; no hidden assumption it is whole body.
    streams=defaultdict(bytearray);previous_type='<start>'
    for e in batch:
        for k,v in e['properties'].items():
            key=(k,type(v).__name__,e['name'],previous_type)
            token=wire.jdump(v).encode('utf-8');streams[key]+=wire.uvarint(len(token))+token
        previous_type=e['name']
    return streams

def main():
    out={}
    for name,make in [('base',lambda seed,n:dataset(seed,installs=n)),('rich',lambda seed,n:dataset(seed,installs=n,rich=True)),('alt',lambda seed,n:dataset_alt(seed,installs=n))]:
        test=make(101,2);tr=make(202,8);xs=samples(test);ts=samples(tr);dc=train(ts)
        n=sum(len(b) for _,bs in test for b in bs);nb=len(xs)
        # Static dictionary per batch-size class. Each candidate trained independently.
        pools=[[],[],[]]
        for i,bs in tr:
            for b in bs:pools[0 if len(b)<=10 else 1 if len(b)<50 else 2].append(wire.mtb2_encode(i,b))
        ds=[train(p) if len(p)>=8 else dc for p in pools];size=0
        for i,bs in test:
            for b in bs:
                raw=wire.mtb2_encode(i,b);di=0 if len(b)<=10 else 1 if len(b)<50 else 2
                size+=len(comp(19,ds[di]).compress(raw))+2
        # History: raw-content dictionary retains 4 preceding acknowledged payloads;
        # baseline trained bytes are included as raw prefix; this loses trained entropy tables.
        history_size=0;baseline=0;retry_extra={str(p):0 for p in (0,.01,.05,.2)}
        for i,bs in test:
            previous=[]
            for b in bs:
                raw=wire.mtb2_encode(i,b);a=len(comp(19,dc).compress(raw))+2;baseline+=a
                if previous:
                    dd=z.ZstdCompressionDict(dc.as_bytes()+b''.join(previous[-4:]),dict_type=z.DICT_TYPE_RAWCONTENT)
                    h=len(comp(19,dd).compress(raw))+2+8 # authenticated reference id
                    h=min(h,a) # per-frame mode flag inside 2-byte prefix
                else:h=a
                history_size+=h
                for p in (0,.01,.05,.2):retry_extra[str(p)]+=h+p*a
                previous.append(raw)
        # Field-conditioned context arithmetic. Train prior by exact field/type/event-name.
        train_fields=[fields(b) for _,bs in tr for b in bs];keys=sorted(set().union(*(f.keys() for f in train_fields)))
        keyids={k:i for i,k in enumerate(keys)};priors={}
        for f in train_fields:
            for k,t in f.items():
                prev=256
                for byte in t:priors.setdefault((keyids[k],prev),Counter())[byte]+=1;prev=byte
        ac_total=zc_total=0;source=0;elapsed=0;count=0
        for _,bs in test:
            for b in bs[:3]:
                f=fields(b);ordered=sorted(f);streams=[bytes(f[k]) for k in ordered]
                p={(j,prev):c for j,k in enumerate(ordered) if k in keyids for (kid,prev),c in priors.items() if kid==keyids[k]}
                t=time.perf_counter();c=code(streams,p);assert code([b'']*len(streams),p,decode=c,lengths=list(map(len,streams)))==streams
                elapsed+=time.perf_counter()-t;count+=1;ac_total+=len(c);source+=sum(map(len,streams));zc_total+=len(comp(19).compress(b''.join(streams)))
        # Integer column byte counts (uncompressed): no cross-compressor attribution.
        totals=Counter()
        for _,bs in test:
            for b in bs:
                cols=defaultdict(list)
                for e in b:
                    for k,v in e['properties'].items():
                        if type(v) is int and v>=0:cols[k].append(v)
                for vals in cols.values():
                    totals['varint']+=sum(len(wire.uvarint(v)) for v in vals)
                    w=max(vals).bit_length();totals['bitpack']+=1+math.ceil(len(vals)*w/8)
                    # EF requires sorted monotone values, so only evaluate applicable columns.
                    if vals==sorted(vals):
                        universe=max(vals)-min(vals)+1;m=len(vals);l=max(0,math.floor(math.log2(universe/m)))
                        totals['ef_applicable_varint']+=sum(len(wire.uvarint(v)) for v in vals)
                        totals['ef']+=len(wire.uvarint(min(vals)))+2+math.ceil((m*l+m+(universe>>l))/8)
                    # Roaring-style dense container lower implementation size on tiny universe:
                    totals['bitmap_set']+=4+min(2*len(set(vals)),math.ceil((max(vals)+1)/8))
                    totals['ordered_values']+=len(vals)
        out[name]={'events':n,'batches':nb,'dict16_B_event':baseline/n,'multi3_dict16_B_event':size/n,'history4_B_event':history_size/n,
                   'history_with_reference_miss_B_event':{p:v/n for p,v in retry_extra.items()},
                   'field_arithmetic':{'bytes':ac_total,'zstd_no_dict_bytes':zc_total,'raw_value_bytes':source,'batches':count,'encode_decode_us_batch':elapsed*1e6/count,'model_json_bytes':len(json.dumps({str(k):dict(v) for k,v in priors.items()}))},'integer_columns':dict(totals)}
        (ROOT/'results/further.json').write_text(json.dumps(out,indent=2));print(name,json.dumps(out[name]),flush=True)
if __name__=='__main__':main()
