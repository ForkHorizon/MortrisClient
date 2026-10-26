"""C#/Python exact table-mode fixtures and host allocation measurements."""
import copy,json,random,string,uuid
from decimal import Decimal
from support7 import ROOT,Reader,v6,make,rebatch,z
from transport7 import Catalog
from native_check7 import fixture
from game_cleanup import cleaned
from real_data import load
import string7

def run():
    ds=rebatch(make('base',2803,1),100);inst,bs=ds[0];source=bs[0][0]
    d=z.ZstdCompressionDict((ROOT/'fixtures/native-base100.dict').read_bytes())
    rng=random.Random(2803);batch=[]
    for i in range(100):
        e=copy.deepcopy(source);e.update(sequence=i+1,ts=e['ts']+i*20,session_elapsed_ms=e['session_elapsed_ms']+i*20,event_id=str(uuid.UUID(int=i+5000)))
        e['properties']={'direct':''.join(rng.choices(string.ascii_uppercase,k=20)),
                         'prefix':'prefix-遊戲-'+str(i)+'-common-suffix',
                         'uuid':str(uuid.UUID(int=rng.getrandbits(128))),
                         'hex':f'{rng.getrandbits(128):032x}',
                         'mixed':''if i==0 else str(uuid.UUID(int=rng.getrandbits(128))),
                         'decimal':Decimal('-0.0000')if i%2 else Decimal('1.2300')}
        batch.append(e)
    c=Catalog.train('table_modes',[(inst,[batch])],logical_strings=True)
    row=fixture('table-modes100',inst,batch,c,d,True,True)
    raw=(ROOT/'fixtures/table-modes100.raw').read_bytes();r=Reader(raw)
    for _ in range(5):v6.readintegers(r,100)
    r.take(1600);modes=[]
    for key,t in c.shapes[0][1]:
        modes.append(r.b[r.p]);assert string7.decode(r,t,100)==[e['properties'][key]for e in batch]
    r.end();assert set(modes)=={0,1,2,3,4},modes
    row['string_modes_exercised']=modes;results=[row]
    large=[]
    for i in range(500):
        e=copy.deepcopy(source);e.update(sequence=i+1,ts=e['ts']+i*20,session_elapsed_ms=e['session_elapsed_ms']+i*20,event_id=str(uuid.UUID(int=i+6000)),properties={'counter':i,'text':('é'if i%2 else'ê')+'🙂'*230+str(i),'case':'ABCDEF'if i%2 else'a b c d'})
        large.append(e)
    lc=Catalog.train('table500',[(inst,[large])],logical_strings=True)
    results.append(fixture('table-unicode500',inst,large,lc,d,True,True))
    train,test=load()
    for variant in ('raw','all_clean'):
        tr=train if variant=='raw'else cleaned(train,migrate_interactions=True)
        te=test if variant=='raw'else cleaned(test,migrate_interactions=True)
        logical=variant=='raw';name='logical_strings'if logical else'strings'
        rc=Catalog.train('puzzle_gravity_test',tr,logical_strings=logical)
        ri,rbs=next((i,bs)for i,bs in te if len(bs[0])==100);rb=rbs[0]
        rd=z.ZstdCompressionDict((ROOT/'results/private'/f'tables-{variant}-{name}-16384.dict').read_bytes())
        label='table-real-'+variant
        results.append(fixture(label,ri,rb,rc,rd,True,True))
        for p in (ROOT/'fixtures').glob(label+'.*'):p.rename(ROOT/'results/private'/p.name)
    assert len(results)==4 and all(r['gc_bytes']==0 and r['python_roundtrip']and r['python_raw_parity']for r in results)
    (ROOT/'results/native-tables.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))

if __name__=='__main__':run()
