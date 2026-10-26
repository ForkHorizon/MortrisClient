"""Identical cadence and header model for V3/V4, explicit model, no pcap."""
import json,uuid
from pathlib import Path
import zstandard as z
import core,wire,framing
from workloads import make
from codec import safe_payload
from frame import pack as pack3
from network import cut,hpack_size,wire_total
ROOT=Path(__file__).resolve().parent
inst,bs=make('base',101,1)[0];original=[e for b in bs for e in b][:900]
d3=z.ZstdCompressionDict((ROOT.parents[1]/'transport-v3/06-experiments/results/dict64_batch100_base.bin').read_bytes());d4=z.ZstdCompressionDict((ROOT/'results/dict-base-trailer.bin').read_bytes())
out={'hpack_never_indexed':hpack_size(),'model':'V3 network.py assumptions, ACK2B, TLS records only on TCP; headers path lengths equal','patterns':{}}
for pattern in ['dense_1s','sparse_45s','short_8','offline_900']:
 events=[]
 for i,e in enumerate(original):
  t=1790000000000+i*(45000 if pattern=='sparse_45s' else 1000)
  if pattern=='short_8':t=1790000000000+(i//8)*600000+(i%8)*1000
  events.append({**e,'ts':t,'session_id':original[0]['session_id'] if pattern!='short_8' else str(uuid.UUID(int=i//8+1))})
 rows={}
 for deadline in [30000,60000,120000]:
  chunks=[events[k:k+100] for k in range(0,len(events),100)] if pattern=='offline_900' else cut(events,100,deadline)
  counts={model:{'body_bytes':0,'wire':{}} for model in ['V3','V4']}
  for b in chunks:
   kind,r=safe_payload(inst,b);body3=len(pack3(kind,r,d3,1));r,t=core.encode(inst,b,trailer=True);body4=len(framing.pack(r,t,len(b),d4,1,19))
   for model,body in [('V3',body3),('V4',body4)]:
    counts[model]['body_bytes']+=body
    for protocol in ['h1','h2','h3']:
     for setup in [0,750,4500]:
      key=f'{protocol}_setup{setup}';counts[model]['wire'][key]=counts[model]['wire'].get(key,0)+wire_total(body,2,len(b),protocol,setup,0,out['hpack_never_indexed'][-1])*len(b)
  rows[str(deadline)]={'events':len(events),'batches':len(chunks),'models':{m:{'body_B_per_event':x['body_bytes']/len(events),'wire_B_per_event':{k:v/len(events) for k,v in x['wire'].items()}} for m,x in counts.items()}}
 out['patterns'][pattern]=rows
(ROOT/'results/network-v4.json').write_text(json.dumps(out,indent=2))
# Actual complete fixture with trained dictionary, including random trailer.
b=original[:20];raw,tail=core.encode(inst,b,trailer=True);f=framing.pack(raw,tail,len(b),d4,1,19)
(ROOT/'results/example-frame.bin').write_bytes(f);(ROOT/'results/example-core.bin').write_bytes(raw);(ROOT/'results/example-trailer.bin').write_bytes(tail);(ROOT/'results/example-source.json').write_bytes(wire.v1_json(inst,b,True))
(ROOT/'results/example.json').write_text(json.dumps({'events':len(b),'frame_bytes':len(f),'core_bytes':len(raw),'trailer_bytes':len(tail),'frame_hex':f.hex(' ')},indent=2))
