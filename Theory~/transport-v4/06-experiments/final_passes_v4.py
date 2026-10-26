"""Two narrow final passes on validation, not a proof of global optimality."""
import json
from pathlib import Path
import zstandard as z
from workloads import make,rebatch
from bench_v4 import CONFIGS,blobs
from framing import pack,unpack,compressor
from primitives import u
ROOT=Path(__file__).resolve().parent
out={}
for p in ['base','rich','alt']:
 xs=blobs(rebatch(make(p,303,3),100),'trailer');d=z.ZstdCompressionDict((ROOT/'results'/f'dict-{p}-trailer.bin').read_bytes());n=sum(len(b) for _,b,_,_ in xs)
 base=sum(len(pack(r,t,len(b),d,1,19)) for _,b,r,t in xs)
 row={'events':n,'base_bytes':base,'base_B_per_event':base/n,'passes':{}}
 # Isolate zstd tuning on same pre-trained bytes, include normal full envelope.
 cp=z.ZstdCompressionParameters.from_level(19,format=z.FORMAT_ZSTD1_MAGICLESS,write_content_size=False,write_checksum=False,write_dict_id=False,window_log=20,enable_ldm=True)
 for label,ctx in [('ultra22',compressor(22,d)),('ldm19',z.ZstdCompressor(compression_params=cp,dict_data=d))]:
  total=0
  for _,b,r,t in xs:
   f=pack(r,t,len(b),d,1,context=ctx);assert unpack(f,{1:d})[1:3]==(r,t);total+=len(f)
  row['passes'][label]={'bytes':total,'improvement_pct':100*(1-total/base)}
 out[p]=row
(ROOT/'results/final-passes-v4.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
