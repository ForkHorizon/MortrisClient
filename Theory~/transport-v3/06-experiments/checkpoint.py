"""Generic same-length sparse string edits, full literal fallback; value-stage only."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'transport-v2/04-experiments'))
from alternate import dataset_alt
from gen import dataset
import msgpack,zstandard as z
out={}
for name,ds in [('base',dataset(101,installs=2)),('rich',dataset(101,installs=2,rich=True)),('alt',dataset_alt(101,installs=2))]:
 raw_bytes=delta_bytes=count=0
 for _,bs in ds:
  for b in bs:
   previous={};literals=[];encoded=[]
   for e in b:
    for k,v in e['properties'].items():
     if not isinstance(v,str):continue
     prev=previous.get(k);literal=msgpack.packb([0,v]);chosen=literal
     if prev is not None and len(prev)==len(v):
      edits=[[i,ch] for i,ch in enumerate(v) if ch!=prev[i]];candidate=msgpack.packb([1,edits])
      if len(candidate)<len(literal):chosen=candidate
     op=msgpack.unpackb(chosen,raw=False)
     if op[0]==0:restored=op[1]
     else:
      p=list(prev)
      for i,ch in op[1]:p[i]=ch
      restored=''.join(p)
     assert restored==v
     previous[k]=v;literals.append([k,v]);encoded.append([k,chosen]);count+=1
   raw_bytes+=len(z.ZstdCompressor(level=19).compress(msgpack.packb(literals)))
   delta_bytes+=len(z.ZstdCompressor(level=19).compress(msgpack.packb(encoded)))
 out[name]={'string_values':count,'zstd_literals_bytes':raw_bytes,'zstd_sparse_bytes':delta_bytes,'note':'value stage, no dict, different representation; not additive with whole-frame savings'}
print(json.dumps(out,indent=2))
