import hashlib,json
from pathlib import Path
from support import make,rebatch,drift
from frame_v5 import render
ROOT=Path(__file__).resolve().parent;out={}
for p in ['base','rich','alt','drift']:
 rows={}
 for name,seed,n in [('train',202,18),('historical',101,6),('validation',303,3),('fresh_holdout',1729,6)]:
  if p=='drift':
   if name=='historical':seed=808;n=4
   elif name=='fresh_holdout':seed=1733;n=4
   elif name=='train':n=12
   ds=drift(seed,n,600)
  else:ds=rebatch(make(p,seed,n),100)
  h=hashlib.sha256();ev=nb=0
  for i,bs in ds:
   for b in bs:
    raw=render(i.install_id,b);h.update(len(raw).to_bytes(8,'little'));h.update(raw);ev+=len(b);nb+=1
  rows[name]={'seed':seed,'installs':n,'events':ev,'batches':nb,'source_length_prefixed_sha256':h.hexdigest()}
 out[p]=rows
(ROOT/'results/corpus-manifest.json').write_text(json.dumps(out,indent=2))
