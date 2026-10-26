"""Transport budget under explicit synthetic arrival patterns, not a pcap.
HPACK authorization never indexed; H3 is parametric estimate, no fictitious TLS records.
"""
import sys,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'transport-v2/04-experiments'))
import wire,hpack,zstandard as z
from gen import dataset
from frame import pack
from codec import safe_payload

def cut(events,cap,deadline):
    batches=[];pending=[]
    for e in events:
        if pending and (e['ts']-pending[0]['ts']>=deadline or e['session_id']!=pending[0]['session_id']):batches.append(pending);pending=[]
        pending.append(e)
        if len(pending)>=cap:batches.append(pending);pending=[]
    if pending:batches.append(pending)
    return batches

def hpack_size():
    h=hpack.Encoder();out=[]
    for i in range(3):
        headers=[(':method','POST'),(':scheme','https'),(':authority','analytics.example'),(':path','/v3/b'),('authorization','Bearer '+'A'*43,True),('content-length',str(700+i))]
        out.append(len(h.encode(headers)))
    return out

def wire_total(body,reply,n,protocol,setup,loss,headers):
    if protocol=='h1':up=body+170;down=reply+90
    elif protocol=='h2':up=body+headers+18;down=reply+20+18
    else: # H3 HTTP frames + QPACK estimate; packet overhead UDP/IP(48)+QUIC(31)
        up=body+headers+6;down=reply+20+6
        overhead=79*(math.ceil(up/1200)+math.ceil(down/1200)+2)
        return ((up+down+overhead+setup)/(1-loss))/n
    up+=22;down+=22
    overhead=52*(math.ceil(up/1400)+math.ceil(down/1400)+2)
    return (up+down+overhead+setup)/(1-loss)/n

def main():
    inst,bs=dataset(101,installs=1)[0];ev=[e for b in bs for e in b][:900]
    dc=z.ZstdCompressionDict((ROOT/'results/dict64_base.bin').read_bytes());out={'hpack_never_indexed':hpack_size(),'patterns':{}}
    for pattern in ('dense_1s','sparse_45s','short_8','offline_900'):
        events=[]
        for i,e in enumerate(ev):
            ts=1790000000000+i*(45000 if pattern=='sparse_45s' else 1000)
            if pattern=='short_8':ts=1790000000000+(i//8)*600000+(i%8)*1000
            events.append({**e,'ts':ts,'session_id':ev[0]['session_id'] if pattern!='short_8' else str(__import__('uuid').UUID(int=i//8+1))})
        rows={}
        for deadline in (30000,60000,120000):
            chunks=[events[i:i+100] for i in range(0,len(events),100)] if pattern=='offline_900' else cut(events,100,deadline)
            totalbody=0;totals={}
            for b in chunks:
                kind,raw=safe_payload(inst,b);body=len(pack(kind,raw,dc,1));totalbody+=body
                for proto in ('h1','h2','h3'):
                    for setup in (0,750,4500):
                        key=f'{proto}_setup{setup}'
                        totals[key]=totals.get(key,0)+wire_total(body,2,len(b),proto,setup,0,out['hpack_never_indexed'][-1])*len(b)
            rows[str(deadline)]={'events':len(events),'batches':len(chunks),'mean_batch':len(events)/len(chunks),'body_B_event':totalbody/len(events),'total_B_event':{k:v/len(events) for k,v in totals.items()}}
        out['patterns'][pattern]=rows
    out['loss_multiplier']={str(p):1/(1-p) for p in (0,.01,.05,.2)}
    # separate policy call saved per 3600s, explicit byte assumption, varies event rate
    out['piggyback_policy_savings_B_event_estimate']={str(rate):800/(rate*3600) for rate in (1,1/45,1/300)}
    print(json.dumps(out,indent=2))
if __name__=='__main__':main()
