"""Two stopping passes on the best measured extreme, paired own-trained dicts."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'transport-v2/04-experiments'))
from gen import dataset
from alternate import dataset_alt
from bench import rebatch,train,comp
from codec import transform
from frame import pack
import wire,zstandard as z
out={}
for name,make in [('base',lambda seed,n:dataset(seed,installs=n)),('rich',lambda seed,n:dataset(seed,installs=n,rich=True)),('alt',lambda seed,n:dataset_alt(seed,installs=n))]:
 test=rebatch(make(101,6),500);tr=rebatch(make(202,18),500);n=sum(len(b) for _,bs in test for b in bs)
 def get(ds,mode=None):return [b'\x01'+wire.mtb2_encode(i,transform(transform(b,'replay_hash'),mode) if mode else transform(b,'replay_hash')) for i,bs in ds for b in bs]
 raw=get(test);d=z.ZstdCompressionDict((ROOT/'results'/('dict64_extreme_'+name+'.bin')).read_bytes());row={'best':sum(len(pack(2,r,d,1)) for r in raw)/n}
 for mode in ('linear','per_type'):
  dd=train(get(tr,mode),65536);r=get(test,mode);row[mode]=sum(len(pack(2,x,dd,1)) for x in r)/n
 for label,lvl,ldm in [('ultra22',22,False),('ldm19',19,True)]:
  row[label]=sum(3+len(wire.uvarint(len(r)))+len(comp(lvl,d,ldm).compress(r)) for r in raw)/n
 out[name]=row;(ROOT/'results/final-passes.json').write_text(json.dumps(out,indent=2));print(name,json.dumps(row),flush=True)
