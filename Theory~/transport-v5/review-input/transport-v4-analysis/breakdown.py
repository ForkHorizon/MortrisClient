import sys
from evalctx import *
name=sys.argv[1];cap=int(sys.argv[2]);hr=len(sys.argv)>3
snap=train(name,cap,hr);costs={}
r=evaluate(name,'test101',cap,snap,stateful=True,hash_rule=hr,verify=False,costs=costs)
print(r)
tot=sum(costs.values())
for k,v in sorted(costs.items(),key=lambda x:-x[1])[:30]:print(f'{str(k):40s} {v/8/r["events"]:7.3f} B/ev {100*v/tot:5.1f}%')
