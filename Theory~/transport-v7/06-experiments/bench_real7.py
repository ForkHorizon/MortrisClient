from support7 import canonical_source,project_source
"""Production DB snapshot, install-disjoint training, true semantic cleanup."""
import gzip, hashlib, json, time, statistics
from collections import Counter
from support7 import ROOT,v6,core,z
from transport7 import Catalog,Aliases,encode,decode,raw_encode,shape
from game_cleanup import cleaned
from bench7 import samples
from real_data import load
from framing import pack,unpack

R=ROOT/'results'

def run():
    train,test=load();rows=[]
    for variant in ('raw','hash_wave_clean','all_clean'):
        tr=train if variant=='raw' else cleaned(train,migrate_interactions=variant=='all_clean')
        te=test if variant=='raw' else cleaned(test,migrate_interactions=variant=='all_clean')
        c=Catalog.train('puzzle_gravity_test',tr);(R/f'catalog-real-{variant}.json').write_bytes(c.data)
        training=samples(c,tr)
        dictionaries={size:z.train_dictionary(size,training,level=1) for size in (16384,32768)}
        for size,d in dictionaries.items():(R/f'dict-real-{variant}-{size}.bin').write_bytes(d.as_bytes())
        v4dict=z.train_dictionary(65536,[core.encode(i,b,trailer=True)[0] for i,bs in tr for b in bs],level=19)
        vc=v6.Schema.train(tr)
        totals=Counter();n=nb=setup=misses=0;timing=[];digest=hashlib.sha256();fixtures=0
        for inst,bs in te:
            a,server=Aliases(bytes(8)),Aliases(bytes(8))
            for b in bs:
                n+=len(b);nb+=1
                src=project_source(c.project,inst.install_id,b,True);digest.update(len(src).to_bytes(8,'little'));digest.update(src)
                totals['v1_json']+=len(src);gz=len(gzip.compress(src,1,mtime=0));totals['v1_gzip1']+=gz
                payload=a.register(inst.install_id,b)
                if payload:server.accept(payload);setup+=len(payload)+8+len(v6.u(len(a.records)))
                totals['v6_zstd1']+=len(v6.encode(vc,a,inst.install_id,b))
                raw,tail=core.encode(inst,b,trailer=True);f=pack(raw,tail,len(b),v4dict,1,19)
                _,rr,tt,_=unpack(f,{1:v4dict});_,ev=core.decode(rr,tt)
                assert v6.render(inst.install_id,ev)==v6.render(inst.install_id,b)
                totals['v4_zstd19']+=len(f)
                modes=[('v7_nodict',None,False),('v7_dict16',dictionaries[16384],False),('v7_dict32',dictionaries[32768],False),('v7_full_ids_dict16',dictionaries[16384],True)]
                if any(shape(e) not in c.ids for e in b):
                    misses+=len(b)
                    for mode,_,_ in modes:totals[mode]+=gz
                    continue
                for mode,d,full in modes:
                    start=time.perf_counter_ns();f=encode(c,a,inst.install_id,b,d,full);elapsed=(time.perf_counter_ns()-start)/1e6
                    o,ev=decode(c,server,f,d,authorized_project=c.project,authorized_origin=inst.install_id)
                    assert canonical_source(o,ev,full)==canonical_source(inst.install_id,b,full)
                    totals[mode]+=len(f)
                    if mode=='v7_dict16' and len(b)==100:timing.append(elapsed)
                if fixtures==0 and len(b)==100:
                    # Actual event values remain private; run full C# value-column parity on this batch.
                    from native_check7 import fixture
                    public=ROOT/'fixtures';private=R/'private';label='real-'+variant
                    native=fixture(label,inst,b,c,dictionaries[16384])
                    for path in public.glob(label+'.*'):path.rename(private/path.name)
                    (R/f'native-{label}.json').write_text(json.dumps(native,indent=2));fixtures+=1
        row={'variant':variant,'events':n,'batches':nb,'source_sha256':digest.hexdigest(),'train_events':sum(len(b)for _,bs in tr for b in bs),
             'schema_shapes':len(c.shapes),'schema_bytes':len(c.data),'fallback_events':misses,'bytes':dict(totals),
             'B_event':{k:v/n for k,v in totals.items()},'alias_setup_bytes':setup,
             'dict16_setup_inclusive_B_event':(totals['v7_dict16']+setup+len(c.data)+16384)/n,
             'python_host_encode100_ms':{'p50':statistics.median(timing),'p95':sorted(timing)[int(.95*(len(timing)-1))]} if timing else None}
        rows.append(row);(R/'bench-real.json').write_text(json.dumps({'rows':rows,'note':'Reconstructed bodies from stored DB events, not captured HTTP; cold schema misses use full V1 gzip.'},indent=2))
        print(json.dumps(row),flush=True)
if __name__=='__main__':run()
