"""Further shrink tables/strategy/dictionary on validation303; not a holdout claim."""
import json
from pathlib import Path
import zstandard as z
from bench_v4 import blobs
from workloads import make,rebatch
from framing import unpack
from primitives import u
ROOT=Path(__file__).resolve().parent;out={}
for p in ['base','rich','alt']:
 xs=blobs(rebatch(make(p,303,3),100),'trailer');n=sum(len(b) for _,b,_,_ in xs);train=blobs(rebatch(make(p,202,18),100),'trailer');row=[]
 for size in [16384,65536]:
  d=z.train_dictionary(size,[r for _,_,r,_ in train],level=19) if size==16384 else z.ZstdCompressionDict((ROOT/'results'/f'dict-{p}-trailer.bin').read_bytes())
  for log in [10,11,12]:
   cp=z.ZstdCompressionParameters.from_level(1,format=z.FORMAT_ZSTD1_MAGICLESS,write_content_size=False,write_checksum=False,write_dict_id=False,window_log=14,hash_log=log,chain_log=log,strategy=z.STRATEGY_FAST)
   ctx=z.ZstdCompressor(compression_params=cp,dict_data=d);total=peak=0
   for _,b,r,t in xs:
    c=ctx.compress(r);frame=b'\x42\x01'+u(len(b))+b'\x01'+u(len(r))+u(len(t))+c+t
    assert unpack(frame,{1:d})[1:3]==(r,t);total+=len(frame);peak=max(peak,ctx.memory_size())
   row.append({'dictionary_bytes':size,'hash_log':log,'chain_log':log,'window_log':14,'strategy':'fast','B_per_event':total/n,'CCtx_size_max':peak,'events':n,'seed':303})
 out[p]=row;(ROOT/'results/memory-floor.json').write_text(json.dumps(out,indent=2));print(p,row,flush=True)
