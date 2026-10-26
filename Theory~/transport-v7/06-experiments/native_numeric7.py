"""Candidate C# zero-GC + Python parity; independent Go checks run separately."""
import copy,json,uuid
from decimal import Decimal
from support7 import ROOT,v6,make,rebatch,z
from transport7 import Catalog
from native_check7 import fixture
from bench7 import samples
from game_cleanup import cleaned
from real_data import load

def run():
    ds=rebatch(make('base',2701,1),100);inst,bs=ds[0];b=bs[0];c=Catalog.train('numeric_native',ds)
    d=z.train_dictionary(4096,samples(c,ds)*3,level=1)
    results=[fixture('candidate-base100',inst,b,c,d,True)]
    edge=copy.deepcopy(b[:3])
    for i,e in enumerate(edge):e['properties']={'integer':[ -(1<<63),(1<<63)-1,0][i],'unsigned':(1<<64)-1,'float':[-0.0,.005,1.25][i],'flag':bool(i%2),'text':'遊戲é🙂','decimal':Decimal('1.2300')}
    ec=Catalog.train('numeric_edge',[(inst,[edge])]);results.append(fixture('candidate-edges',inst,edge,ec,d,True))
    large=[]
    for i in range(500):
        e=copy.deepcopy(b[0]);e.update(sequence=i+1,ts=e['ts']+i*20,session_elapsed_ms=e['session_elapsed_ms']+i*20,event_id=str(uuid.UUID(int=i+1)),properties={'counter':i,'flag':bool(i%2),'text':'遊戲é🙂'+str(i)})
        large.append(e)
    lc=Catalog.train('numeric500',[(inst,[large])]);results.append(fixture('candidate-500',inst,large,lc,d,True))
    import random,numeric7
    from support7 import Reader
    rng=random.Random(2702);forced=[];sequence=0;timestamp=1790000000000;elapsed=0
    for i in range(500):
        sequence+=rng.randint(1,97);timestamp+=rng.randint(1,1000);elapsed+=rng.randint(1,800)
        e=copy.deepcopy(b[0]);e.update(sequence=sequence,ts=timestamp,session_elapsed_ms=elapsed,event_id=str(uuid.UUID(int=i+2000)),properties={'direct':rng.randrange(-(1<<63),(1<<63)),'reference_time':timestamp,'reference_sequence':sequence,'reference_elapsed':elapsed,'value_table':(-(1<<63) if i%2 else (1<<63)-1)})
        forced.append(e)
    fc=Catalog.train('numeric_modes',[(inst,[forced])]);row=fixture('candidate-modes',inst,forced,fc,d,True)
    raw=(ROOT/'fixtures/candidate-modes.raw').read_bytes();reader=Reader(raw)
    for _ in range(5):v6.readintegers(reader,500)
    reader.take(500*16);modes=[]
    for key,_ in fc.shapes[0][1]:
        modes.append(reader.b[reader.p]);numeric7.decode(reader,500,forced)
    reader.end();assert set(modes)=={0,1,2,3,4},modes
    row['numeric_modes_exercised']=modes;results.append(row)
    _,test=load()
    for variant in ('raw','all_clean'):
        current=test if variant=='raw' else cleaned(test,migrate_interactions=True)
        ri,rbs=next((i,bs)for i,bs in current if len(bs[0])==100);rb=rbs[0]
        rc=Catalog.load((ROOT/'results'/f'catalog-real-{variant}.json').read_bytes())
        rd=z.ZstdCompressionDict((ROOT/'results/private'/f'numeric-{variant}-16384.dict').read_bytes())
        label='candidate-real-'+variant
        results.append(fixture(label,ri,rb,rc,rd,True))
        for p in (ROOT/'fixtures').glob(label+'.*'):p.rename(ROOT/'results/private'/p.name)
    (ROOT/'results/native-numeric.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
if __name__=='__main__':run()
