import json,copy
from pathlib import Path
from common import *
import ctxcodec as cc,exact
out={};inst,bs=workload('base','test101',100)[0];b=bs[0][:2]
f,_=cc.encode(cc.Model(),inst.install_id,b)
for label,frame in [('extra_zero',f[:-4]+b'\x00'+f[-4:]),('extra_64_zero',f[:-4]+b'\x00'*64+f[-4:])]:
 try:cc.decode(cc.Model(),frame);out[label+'_accepted']=True
 except Exception:out[label+'_accepted']=False
m=cc.Model();c=cc.Coder(m,True);cc.code_batch(c,inst.install_id,b,False)
out['stateless_last_alias_bug']={'event_state_kept_in_model':('ev',) in m.last,'last_keys':len(m.last)}
s=cc.Model();f,_=cc.encode(s,inst.install_id,b,True);d=cc.Model();cc.decode(d,f,True)
f2,_=cc.encode(s,inst.install_id,bs[1][:2],True);bad=bytearray(f2);bad[-1]^=1
before=copy.deepcopy(d.__dict__)
try:cc.decode(d,bytes(bad),True)
except ValueError:pass
out['failed_decode_mutates_state']=d.__dict__!=before
m=cc.Model();g,_=cc.encode(m,inst.install_id,b,True);g=bytes([g[0],255])+g[2:]
try:cc.decode(cc.Model(),g,True);out['state_token_255_accepted']=True
except ValueError:out['state_token_255_accepted']=False
orig=cc.Coder.sint
def sent_override(s,ctx,v=None):return orig(s,ctx,9999 if s.enc and ctx==('sent',) else v)
cc.Coder.sint=sent_override
c=cc.Coder(cc.Model(),True);cc.code_batch(c,inst.install_id,b,False);body=c.rc.finish();g=bytes([cc.HDR_STATELESS])+body+cc._crc(inst.install_id,b)
cc.Coder.sint=orig
iid,ev=cc.decode(cc.Model(),g);out['sent_delta_9999_lost']=exact.render(inst,ev)==exact.render(inst,b)
print(json.dumps(out,indent=2));Path(__file__).with_name('counterexamples.json').write_text(json.dumps(out,indent=2))
