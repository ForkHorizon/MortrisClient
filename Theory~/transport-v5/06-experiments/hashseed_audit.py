import subprocess,sys,os,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent;SUB=ROOT/'submission-rerun'
script="""import hashlib,json
from common import *
import ctxcodec as cc
import rc
old=cc.Coder.bit
def bit(self,ctx,b=None):
 k=hash(ctx)&16383;pr=self.P.get(k)
 if pr is None:pr=self.P[k]=[32768,32768]
 return self.rc.bit(pr,b)
cc.Coder.bit=bit
inst,bs=workload('base','test101',100)[0]
f,_=cc.encode(cc.Model(),inst.install_id,bs[0][:20])
print(json.dumps({'context_slot':hash((('tap','value'),'M',17,8))&16383,'frame_sha256':hashlib.sha256(f).hexdigest(),'frame_bytes':len(f)}))
"""
rows=[]
for seed in ['0','1','2']:
 env={**os.environ,'PYTHONHASHSEED':seed,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(SUB)}
 row=json.loads(subprocess.check_output([sys.executable,'-c',script],env=env,text=True));row['PYTHONHASHSEED']=seed;rows.append(row)
assert len({v['frame_sha256'] for v in rows})>1
(ROOT/'results/submission-hashseed.json').write_text(json.dumps(rows,indent=2))
