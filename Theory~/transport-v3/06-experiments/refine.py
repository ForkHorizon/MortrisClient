"""Two final passes against current best configuration, not original V2."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'transport-v2/04-experiments'))
from gen import dataset
from alternate import dataset_alt
from bench import rebatch,samples,train,comp
from codec import transform
import wire,zstandard as z
from frame import pack,unpack
out={}
for name,make in [('base',lambda seed,n:dataset(seed,installs=n)),('rich',lambda seed,n:dataset(seed,installs=n,rich=True)),('alt',lambda seed,n:dataset_alt(seed,installs=n))]:
 test=rebatch(make(101,6),100);tr=make(202,18);n=sum(len(b) for _,bs in test for b in bs)
 d=z.ZstdCompressionDict((ROOT/'results'/('dict64_'+name+'.bin')).read_bytes())
 raw=samples(test);retained=sum(len(pack(1,r,d,1)) for r in raw)/n
 d=train(samples(rebatch(tr,100)),65536)
 (ROOT/'results'/('dict64_batch100_'+name+'.bin')).write_bytes(d.as_bytes())
 base=sum(len(pack(1,r,d,1)) for r in raw)/n
 row={'retained':retained,'best':base}
 for label,lvl,ldm in [('ultra22',22,False),('ldm19',19,True)]:
  row[label]=sum(3+len(wire.uvarint(len(r)))+len(comp(lvl,d,ldm).compress(r)) for r in raw)/n
 for mode in ('linear','per_type','xor','prefix'):
  dd=train(samples(rebatch(tr,100),mode),65536)
  rr=samples(test,mode);row[mode]=sum(3+len(wire.uvarint(len(r)))+len(comp(19,dd).compress(r)) for r in rr)/n
 out[name]=row
 print(name,json.dumps(row),flush=True)
 (ROOT/'results/refine.json').write_text(json.dumps(out,indent=2))
