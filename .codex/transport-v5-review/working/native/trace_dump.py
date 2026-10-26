"""Dump the exact binary-decision trace (context hash, bit) of MTB5 stateless encoding for native timing,
plus the trained prior table, plus V4 raw cores for zstd native timing."""
import sys,struct,time,statistics
sys.path.insert(0,'/workspace/transport-v4-analysis')
from evalctx import *
import ctxcodec as cc,rc
import core,framing
import zstandard as z
from bench_v4 import CONFIGS
name=sys.argv[1] if len(sys.argv)>1 else 'base'
snap=train(name,100)
H=lambda ctx:hash(ctx)&0xFFFFFFFFFFFFFFFF
# prior table
with open(f'native/prior_{name}.bin','wb') as f:
    f.write(struct.pack('<I',len(snap.probs)))
    for k,(a,b) in snap.probs.items():f.write(struct.pack('<QHH',H(k),a,b))
# trace
class TCoder(cc.Coder):
    def bit(s,ctx,b=None):
        s.trace.append((H(ctx),1 if b else 0));return super().bit(ctx,b)
te=workload(name,'test101',100);batches=[];sizes=[]
for inst,bs in te:
    for b in bs:
        m=snap.clone();c=TCoder(m,True);c.trace=[];cc.code_batch(c,inst.install_id,b);sizes.append(len(c.rc.finish())+1);batches.append((len(b),c.trace))
with open(f'native/trace_{name}.bin','wb') as f:
    f.write(struct.pack('<I',len(batches)))
    for n,tr in batches:
        f.write(struct.pack('<II',n,len(tr)))
        for h,b in tr:f.write(struct.pack('<QB',h,b))
print('python frame bytes',sum(sizes),'events',sum(n for n,_ in batches))
# zstd native timing on the V4 raw cores (same batches)
tr=workload(name,'train202',100)
d=z.train_dictionary(65536,[core.encode(i,b,**CONFIGS['trailer'])[0] for i,bs in tr for b in bs],level=19)
raws=[core.encode(i,b,**CONFIGS['trailer'])[0] for i,bs in te for b in bs];nev=sum(len(b) for _,bs in te for b in bs)
# structure-only time for V4 python core (reference, not native)
res={}
for lab,ctx in [('zstd_l19_dict64',framing.compressor(19,d)),('zstd_l3_tables12_dict64',z.ZstdCompressor(compression_params=z.ZstdCompressionParameters.from_level(3,format=z.FORMAT_ZSTD1_MAGICLESS,write_content_size=False,write_checksum=False,write_dict_id=False,window_log=17,hash_log=12,chain_log=12),dict_data=d)),('zstd_l1_dict64',framing.compressor(1,d))]:
    best=[]
    for rep in range(5):
        t0=time.perf_counter()
        for r in raws:ctx.compress(r)
        best.append(time.perf_counter()-t0)
    res[lab]={'us_per_event_min_of_5':min(best)/nev*1e6,'B_per_event_payload':sum(len(ctx.compress(r)) for r in raws)/nev,'cctx_bytes':ctx.memory_size()}
print(res)
import json;json.dump(res,open(f'native/zstd_native_{name}.json','w'),indent=1)
