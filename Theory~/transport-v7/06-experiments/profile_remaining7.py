"""Counterfactual constant-column ablation, not a lossless transport candidate.
Uses the frozen numeric dictionary and all held-out events to locate remaining entropy.
"""
from collections import Counter,defaultdict
from decimal import Decimal
import gzip,json
from support7 import ROOT,v6,core,z,Reader,project_source
from transport7 import Catalog,Aliases,shape,raw_encode
from game_cleanup import cleaned
from real_data import load
import numeric7

def zero(t,values):
    if t==core.T_INT or t==core.T_U64:return 0
    if t==core.T_BOOL:return False
    if t==core.T_NULL:return None
    if t in (core.T_F32,core.T_F64):return 0.0
    if t==core.T_UUID:return '00000000-0000-0000-0000-000000000000'
    if t==core.T_HEX:return '00'*(len(values[0])//2)
    if t==core.T_NUMTEXT:return Decimal('0')
    return ''

def run():
    _,test=load();test=cleaned(test,migrate_interactions=True)
    c=Catalog.load((ROOT/'results/catalog-real-all_clean.json').read_bytes())
    d=z.ZstdCompressionDict((ROOT/'results/private/numeric-all_clean-32768.dict').read_bytes())
    compressor=z.ZstdCompressor(level=1,dict_data=d)
    def size(raw,n):return 32+len(v6.u(n))+len(v6.u(len(raw)))+min(len(raw),len(compressor.compress(raw)))
    fields=defaultdict(Counter);baseline=events=encoded=missed=0
    for inst,bs in test:
        a=Aliases(bytes(8))
        for batch in bs:
            n=len(batch);events+=n;a.register(inst.install_id,batch)
            if any(shape(e)not in c.ids for e in batch):
                baseline+=len(gzip.compress(project_source(c.project,inst.install_id,batch,True),1,mtime=0));missed+=n;continue
            encoded+=n;raw=raw_encode(c,a,inst.install_id,batch,False,True);base=size(raw,n);baseline+=base
            owners=defaultdict(list)
            for e in batch:
                for key,t in c.shapes[c.ids[shape(e)]][1]:owners[(key,t)].append(e)
            r=Reader(raw)
            for _ in range(5):v6.readintegers(r,n)
            prefix=raw[:r.p];parts=[]
            for (key,t),rows in owners.items():
                start=r.p
                values=numeric7.decode(r,len(rows),rows)if t==core.T_INT else v6.dec_values(r,t,len(rows))
                assert values==[e['properties'][key]for e in rows]
                constant=[zero(t,values)]*len(rows)
                replacement=numeric7.encode(constant,rows)if t==core.T_INT else v6.enc_values(t,constant)
                parts.append((key,raw[start:r.p],replacement))
                fields[key]['raw_bytes']+=r.p-start;fields[key]['occurrences']+=len(rows)
            r.end()
            for key in {p[0]for p in parts}:
                altered=prefix+b''.join(replacement if k==key else original for k,original,replacement in parts)
                fields[key]['body_saved_if_constant']+=base-size(altered,n)
    expected=json.loads((ROOT/'results/numeric-benchmark.json').read_text())[1]
    assert expected['bytes']['dict32']==baseline,(baseline,expected['bytes']['dict32'])
    rows=[dict(field=key,**dict(v),raw_B_event=v['raw_bytes']/events,marginal_B_event=v['body_saved_if_constant']/events)for key,v in fields.items()]
    rows.sort(key=lambda x:x['marginal_B_event'],reverse=True)
    result={'events':events,'encoded_events':encoded,'fallback_events':missed,'baseline_body_bytes':baseline,'baseline_B_event':baseline/events,
            'warning':'Counterfactual constant values remove information. Marginal gains are not additive or a deployable codec. Original dictionary retained.','fields':rows}
    (ROOT/'results/remaining-column-costs.json').write_text(json.dumps(result,indent=2))
    for row in rows[:15]:print(row['field'],round(row['marginal_B_event'],3),round(row['raw_B_event'],3),flush=True)
if __name__=='__main__':run()
