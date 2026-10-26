import json,hashlib
from pathlib import Path
import core,exact
from workloads import make,drift
ROOT=Path(__file__).resolve().parent;out={}
for p in ['base','rich','alt','drift']:
 rows={}
 for label,seed,n in [('historical',101,6),('train',202,18),('validation',303,3),('holdout',909,6)]:
  if p=='drift':
   if label not in ('train','holdout'):continue
   ds=drift(202,12,600) if label=='train' else drift(808,4,600)
  else:ds=make(p,seed,n)
  digest=hashlib.sha256();events=batches=0
  for inst,bs in ds:
   for b in bs:
    raw=exact.render(inst,b);digest.update(len(raw).to_bytes(8,'little'));digest.update(raw);events+=len(b);batches+=1
  rows[label]={'events':events,'batches':batches,'installs':len(ds),'sha256_V1_minus_id_length_prefixed':digest.hexdigest(),'seed':808 if p=='drift' and label=='holdout' else seed}
 out[p]=rows
(ROOT/'results/corpus-manifest.json').write_text(json.dumps(out,indent=2))
