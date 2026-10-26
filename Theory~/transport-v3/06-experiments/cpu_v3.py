"""Whole Python prototype timings, explicit compressor construction and verification."""
import sys,json,time,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'transport-v2/04-experiments'))
from gen import dataset
from alternate import dataset_alt
from codec import safe_payload
from frame import pack,unpack
import zstandard as z
out={}
for name,ds in [('base',dataset(101,installs=1)),('rich',dataset(101,installs=1,rich=True)),('alt',dataset_alt(101,installs=1))]:
 d=z.ZstdCompressionDict((ROOT/'results'/('dict64_'+name+'.bin')).read_bytes());enc=[];dec=[]
 for i,bs in ds:
  for b in bs[:30]:
   t=time.perf_counter();kind,raw=safe_payload(i,b);f=pack(kind,raw,d,1);enc.append((time.perf_counter()-t)*1e6)
   t=time.perf_counter();assert unpack(f,{1:d})==(kind,raw);dec.append((time.perf_counter()-t)*1e6)
 def stats(xs):return {'p50_us':statistics.median(xs),'p95_us':sorted(xs)[int((len(xs)-1)*.95)],'batches':len(xs)}
 out[name]={'encode_verify_select_frame':stats(enc),'outer_decode_only':stats(dec)}
print(json.dumps(out,indent=2))
