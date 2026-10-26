"""Content hashes and readable fixtures; full corpora regenerate from pinned seeds."""
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'transport-v2/04-experiments'))
from gen import dataset
from alternate import dataset_alt
import wire
(ROOT/'data').mkdir(exist_ok=True);out={}
for name,make in [('base',lambda seed,n:dataset(seed,installs=n)),('rich',lambda seed,n:dataset(seed,installs=n,rich=True)),('alt',lambda seed,n:dataset_alt(seed,installs=n))]:
 out[name]={}
 for split,seed,n in [('test',101,6),('train',202,18)]:
  ds=make(seed,n);h=hashlib.sha256();count=nb=0
  for i,bs in ds:
   for b in bs:
    raw=wire.v1_json(i,b);h.update(len(raw).to_bytes(8,'little'));h.update(raw);count+=len(b);nb+=1
  out[name][split]={'seed':seed,'installs':n,'events':count,'batches':nb,'sha256_length_prefixed_v1':h.hexdigest()}
  if split=='test':
   i,bs=ds[0];ev=[e for b in bs for e in b][:20]
   (ROOT/'data'/(name+'-20events.json')).write_bytes(wire.v1_json(i,ev))
print(json.dumps(out,indent=2))
