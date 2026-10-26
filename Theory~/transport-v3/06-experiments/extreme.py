"""Spec rule1, complete frame roundtrip, cap500. Not a real-game algorithm."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'transport-v2/04-experiments'))
import wire
from gen import dataset
from alternate import dataset_alt
from codec import transform,restore
from bench import samples,rebatch,train
from frame import pack,unpack
out={}
for name,make in [('base',lambda seed,n:dataset(seed,installs=n)),('rich',lambda seed,n:dataset(seed,installs=n,rich=True)),('alt',lambda seed,n:dataset_alt(seed,installs=n))]:
 test=rebatch(make(101,6),500);tr=rebatch(make(202,18),500)
 d=train([b'\x01'+r for r in samples(tr,'replay_hash')],65536)
 size=n=0;nb=0
 for i,bs in test:
  for b in bs:
   raw=b'\x01'+wire.mtb2_encode(i,transform(b,'replay_hash'));f=pack(2,raw,d,1);kind,r=unpack(f,{1:d});assert kind==2 and r[0]==1
   _,ev=wire.mtb2_decode(r[1:]);assert wire.v1_json(i,restore(ev,'replay_hash'),True)==wire.v1_json(i,b,True)
   size+=len(f);n+=len(b);nb+=1
 out[name]={'events':n,'batches':nb,'frame_bytes':size,'B_event':size/n}
 (ROOT/'results'/('dict64_extreme_'+name+'.bin')).write_bytes(d.as_bytes())
 (ROOT/'results/extreme.json').write_text(json.dumps(out,indent=2));print(name,json.dumps(out[name]),flush=True)
