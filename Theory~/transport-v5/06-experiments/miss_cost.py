"""Real decode/recovery simulation plus explicit network model, rather than ideal stateful bytes."""
import json,random
from pathlib import Path
from support import make,rebatch
from model import Model
from recovery import Server,Client,MissingBase
from network import wire_total,hpack_size
ROOT=Path(__file__).resolve().parent;prior=Model.restore((ROOT/'results/prior14-base.bin').read_bytes());out=[]
for rate in [0,.01,.05,.2,.5,1]:
 total=events=requests=misses=0;wire=0;rng=random.Random(1903)
 for inst,bs in rebatch(make('base',1729,2),100):
  server=Server(prior,':memory:',{inst.install_id});client=Client(prior,inst.install_id)
  for j,b in enumerate(bs):
   token=f'{j}';frame=client.begin(token,b)
   if rng.random()<rate and client.state is not None:server.states.clear();server.responses.clear()
   requests+=1;total+=len(frame)
   try:ack=server.receive(frame)
   except MissingBase:
    misses+=1;wire+=wire_total(len(frame),16,len(b),'h2',0,0,hpack_size()[-1])*len(b)
    client.timeout(token);frame=client.begin(token+'-fallback',b,True);token+='-fallback';requests+=1;total+=len(frame);ack=server.receive(frame)
   wire+=wire_total(len(frame),18,len(b),'h2',0,0,hpack_size()[-1])*len(b);assert client.ack(token,ack);events+=len(b)
  assert server.db.execute('select count(*) from e').fetchone()[0]==sum(map(len,bs));server.db.close()
 out.append({'configured_miss_rate':rate,'observed_misses':misses,'requests':requests,'events':events,'body_B_per_event_including_failed_requests':total/events,'warm_H2_B_per_event_model':wire/events})
(ROOT/'results/miss-cost.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
