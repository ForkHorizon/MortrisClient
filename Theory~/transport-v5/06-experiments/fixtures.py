import json,hashlib,subprocess,sys,os
from pathlib import Path
from support import make,rebatch
from model import Model,context_bytes,context_hash
from frame_v5 import encode,decode,render
ROOT=Path(__file__).resolve().parent;prior=Model.restore((ROOT/'results/prior14-base.bin').read_bytes());i,bs=rebatch(make('base',101,1),100)[0];b=bs[0][:20]
f,m=encode(prior,i.install_id,b);assert decode(prior,f)[0]==render(i.install_id,b)
(ROOT/'results/example-frame.bin').write_bytes(f);(ROOT/'results/example-source.json').write_bytes(render(i.install_id,b))
f2,m2=encode(prior,i.install_id,bs[1][:20],base=m);assert decode(prior,f2,base=m)[0]==render(i.install_id,bs[1][:20])
(ROOT/'results/example-stateful-frame.bin').write_bytes(f2);(ROOT/'results/example-base-state.bin').write_bytes(m.snapshot(True))
script="""from pathlib import Path
import hashlib,json
from model import Model
from frame_v5 import decode
r=Path('ROOT_VALUE')/'results'
p=Model.restore((r/'prior14-base.bin').read_bytes())
s,m=decode(p,(r/'example-frame.bin').read_bytes())
print(hashlib.sha256(s).hexdigest()+':'+m.state_id().hex())
""".replace('ROOT_VALUE',str(ROOT))
checks=[]
for seed in ['1','2','random']:
 env={**os.environ,'PYTHONHASHSEED':seed,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT)};checks.append(subprocess.check_output([sys.executable,'-c',script],env=env,text=True).strip())
assert len(set(checks))==1
v=(('tap','value'),'M',17,8)
out={'frame_bytes':len(f),'stateful_frame_bytes':len(f2),'events':20,'frame_hex':f.hex(' '),'source_sha256':hashlib.sha256(render(i.install_id,b)).hexdigest(),'post_state_id':m.state_id().hex(),'cross_process_hashseed_results':checks,'context_vector':{'value':repr(v),'canonical_bytes_hex':context_bytes(v).hex(),'hash_u64':context_hash(v),'slot14':context_hash(v)&16383}}
(ROOT/'results/fixtures.json').write_text(json.dumps(out,indent=2))
