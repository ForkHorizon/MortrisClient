"""Out-of-SDK-contract sensitivity only; separate totals, no production claim."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'transport-v2/04-experiments'))
from alternate import dataset_alt
from bench import train,comp
import wire
out={}
for split,seed,n in [('train',202,6),('test',101,2)]:
 ds=dataset_alt(seed,installs=n);xs=[];count=0
 for i,bs in ds:
  for b in bs:
   transformed=[{**e,'properties':{'字段_'+k:v for k,v in e['properties'].items()}} for e in b]
   raw=wire.mtb2_encode(i,transformed);_,ev=wire.mtb2_decode(raw);assert wire.v1_json(i,ev,True)==wire.v1_json(i,transformed,True)
   xs.append(raw);count+=len(b)
 if split=='train':d=train(xs)
 else:out={'events':count,'B_event_dict16':sum(len(comp(19,d).compress(x))+2 for x in xs)/count,'warning':'Chinese keys rejected by current EventValidator; sensitivity for future contract only'}
print(json.dumps(out,indent=2))
