import random,time,json,struct
from pathlib import Path
from support import make,rebatch
from model import Model
from frame_v5 import encode,decode
ROOT=Path(__file__).resolve().parent
prior=Model.restore((ROOT/'results/prior14-base.bin').read_bytes());i,bs=rebatch(make('base',101,1),100)[0]
frames=[encode(prior,i.install_id,b)[0] for b in bs[:8]];rng=random.Random(1901);stats={'rejected':0,'decoded':0,'attempts':2000,'worst_s':0};unchanged=prior.snapshot()
for k in range(2000):
 f=bytearray(rng.choice(frames));op=k%4
 if op==0:f[rng.randrange(len(f))]^=rng.randrange(1,256)
 elif op==1:f=f[:rng.randrange(1,len(f))]
 elif op==2:f=f[:-4]+rng.randbytes(rng.randrange(1,80))+f[-4:]
 else:f[rng.randrange(24,len(f)-4):]=rng.randbytes(rng.randrange(5,100))
 start=time.perf_counter()
 try:decode(prior,bytes(f),timeout_seconds=.75);stats['decoded']+=1
 except (ValueError,UnicodeError,OverflowError,struct.error):stats['rejected']+=1
 stats['worst_s']=max(stats['worst_s'],time.perf_counter()-start)
assert prior.snapshot()==unchanged
stats['prior_unchanged']=True
(ROOT/'results/mutations.json').write_text(json.dumps(stats,indent=2));print(json.dumps(stats,indent=2))
