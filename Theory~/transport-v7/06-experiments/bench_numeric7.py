"""Train/test the generic numeric candidate without replacing frozen V7 totals."""
import gzip,hashlib,json,time,statistics
from collections import Counter
from support7 import ROOT,v6,z,canonical_source,project_source
from real_data import load
from game_cleanup import cleaned
from transport7 import Catalog,Aliases,shape,raw_encode,encode,decode

def run():
    train,test=load();report=[]
    for variant in ('raw','all_clean'):
        tr=train if variant=='raw' else cleaned(train,migrate_interactions=True)
        te=test if variant=='raw' else cleaned(test,migrate_interactions=True)
        c=Catalog.train('puzzle_gravity_test',tr);samples=[]
        for inst,bs in tr:
            a=Aliases(bytes(8))
            for b in bs:
                a.register(inst.install_id,b)
                samples.append(raw_encode(c,a,inst.install_id,b,False,True))
        ds={size:z.train_dictionary(size,samples,level=1)for size in (16384,32768)}
        for size,d in ds.items():(ROOT/'results/private'/f'numeric-{variant}-{size}.dict').write_bytes(d.as_bytes())
        totals=Counter();n=miss=0;times=[]
        for inst,bs in te:
            a=Aliases(bytes(8))
            for b in bs:
                n+=len(b);a.register(inst.install_id,b)
                modes=[('dict16',ds[16384],False),('dict32',ds[32768],False),('full_ids_dict16',ds[16384],True)]
                if any(shape(e)not in c.ids for e in b):
                    miss+=len(b);fallback=len(gzip.compress(project_source(c.project,inst.install_id,b,True),1,mtime=0))
                    for mode,_,_ in modes:totals[mode]+=fallback
                    continue
                for mode,d,full in modes:
                    start=time.perf_counter_ns();f=encode(c,a,inst.install_id,b,d,full,True);elapsed=(time.perf_counter_ns()-start)/1e6
                    o,ev=decode(c,a,f,d,authorized_project=c.project,authorized_origin=inst.install_id)
                    assert canonical_source(o,ev,full)==canonical_source(o,b,full)
                    totals[mode]+=len(f)
                    if mode=='dict32'and len(b)==100:times.append(elapsed)
        row={'variant':variant,'events':n,'fallback_events':miss,'bytes':dict(totals),'B_event':{k:v/n for k,v in totals.items()},
             'python_host_encode100_ms':{'p50':statistics.median(times),'p95':sorted(times)[int(.95*(len(times)-1))]},
             'dictionary_sha256':{str(size):hashlib.sha256(d.as_bytes()).hexdigest()for size,d in ds.items()},
             'native_verification':'native-numeric.json and go-check-numeric.json','Unity_IL2CPP':'NOT_MEASURED'}
        report.append(row);(ROOT/'results/numeric-benchmark.json').write_text(json.dumps(report,indent=2));print(json.dumps(row),flush=True)
if __name__=='__main__':run()
