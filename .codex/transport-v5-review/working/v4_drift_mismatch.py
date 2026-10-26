from common import *
import core,framing,exact,json
import zstandard as z
from bench_v4 import CONFIGS
tr=workload('base','train202',100);d=z.train_dictionary(65536,[core.encode(i,b,**CONFIGS['trailer'])[0] for i,bs in tr for b in bs],level=19)
te=workload('drift','hold909',0);n=tot=0
for inst,bs in te:
    for b in bs:
        r,t=core.encode(inst,b,**CONFIGS['trailer']);f=framing.pack(r,t,len(b),d,1,19);n+=len(b);tot+=len(f)
print(json.dumps({'V4_drift_with_base_dict_B_per_event':tot/n}))
