"""Explicit wire model, full V5 frames; experimental stateful ACK is18B, stateless2B."""
import json,uuid
from pathlib import Path
import zstandard as z
from support import make,rebatch,core
from model import Model
from frame_v5 import encode,decode,render
from framing import pack
from network import cut,hpack_size,wire_total
ROOT=Path(__file__).resolve().parent
i,bs=make('base',1729,1)[0];events=[e for b in bs for e in b][:900];prior=Model.restore((ROOT/'results/prior14-base.bin').read_bytes())
d=z.ZstdCompressionDict((ROOT.parents[1]/'transport-v4/06-experiments/results/dict-base-trailer.bin').read_bytes());out={'seed':1729,'ACK_bytes':{'V4':2,'V5_stateless':2,'V5_stateful':18},'hpack':hpack_size(),'patterns':{}}
for pattern in ['dense_1s','sparse_45s','short_8','offline_900']:
 ev=[]
 for j,e in enumerate(events):
  ts=1790000000000+j*(45000 if pattern=='sparse_45s' else 1000)
  if pattern=='short_8':ts=1790000000000+(j//8)*600000+(j%8)*1000
  ev.append({**e,'ts':ts,'session_id':events[0]['session_id'] if pattern!='short_8' else str(uuid.UUID(int=j//8+1))})
 chunks=[ev[k:k+100] for k in range(0,len(ev),100)] if pattern=='offline_900' else cut(ev,100,30000)
 counts={name:{'body_bytes':0,'wire':{}} for name in out['ACK_bytes']};em=dm=None
 for b in chunks:
  raw,tail=core.encode(i,b,trailer=True);f4=pack(raw,tail,len(b),d,1,19)
  f,m=encode(prior,i.install_id,b);assert decode(prior,f)[0]==render(i.install_id,b)
  fs,em=encode(prior,i.install_id,b,base=em);source,dm=decode(prior,fs,base=dm);assert source==render(i.install_id,b)
  for label,frame in [('V4',f4),('V5_stateless',f),('V5_stateful',fs)]:
   counts[label]['body_bytes']+=len(frame)
   for protocol in ['h1','h2','h3']:
    for setup in [0,750,4500]:
     key=f'{protocol}_setup{setup}';counts[label]['wire'][key]=counts[label]['wire'].get(key,0)+wire_total(len(frame),out['ACK_bytes'][label],len(b),protocol,setup,0,out['hpack'][-1])*len(b)
 out['patterns'][pattern]={'events':len(ev),'batches':len(chunks),'models':{k:{'body_B_per_event':v['body_bytes']/len(ev),'wire_B_per_event':{k:x/len(ev) for k,x in v['wire'].items()}} for k,v in counts.items()}}
(ROOT/'results/network.json').write_text(json.dumps(out,indent=2))
