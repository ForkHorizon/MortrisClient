"""Train-only dictionaries for generic cross-column residuals; paid framing allowance.
This raw-codec probe does not add an M7 capability or change SDK/native code.
"""
import gzip,hashlib,json,statistics,time
from collections import Counter
from support7 import ROOT,z,v6,project_source
from transport7 import Catalog,Aliases,raw_encode
from game_cleanup import cleaned
from real_data import load
import cross7

def body_size(raw,n,compressor):
    comp=compressor.compress(raw)
    return 32+len(v6.u(n))+len(v6.u(len(raw)))+min(len(raw),len(comp)),comp

def run():
    train,test=load();results=[]
    baseline=json.loads((ROOT/'results/tables-benchmark.json').read_text())
    for variant in ('raw','all_clean'):
        tr=train if variant=='raw'else cleaned(train,migrate_interactions=True)
        te=test if variant=='raw'else cleaned(test,migrate_interactions=True)
        logical=variant=='raw';model='logical_strings'if logical else'strings'
        c=Catalog.train('puzzle_gravity_test',tr,logical_strings=logical);samples=[]
        for inst,bs in tr:
            a=Aliases(bytes(8))
            for b in bs:
                a.register(inst.install_id,b);base=raw_encode(c,a,inst.install_id,b,False,True,True)
                packed,_=cross7.rewrite(base,c,b);samples.append(packed)
        dictionaries={size:z.train_dictionary(size,samples,level=1)for size in (16384,32768)}
        for size,d in dictionaries.items():(ROOT/'results/private'/f'cross-{variant}-{size}.dict').write_bytes(d.as_bytes())
        compressors={size:z.ZstdCompressor(level=1,dict_data=d)for size,d in dictionaries.items()}
        old={size:z.ZstdCompressor(level=1,dict_data=z.ZstdCompressionDict((ROOT/'results/private'/f'tables-{variant}-{model}-{size}.dict').read_bytes()))for size in dictionaries}
        totals=Counter();base_totals=Counter();modes=Counter();n=miss=0;times=[]
        for inst,bs in te:
            a=Aliases(bytes(8))
            for b in bs:
                n+=len(b);a.register(inst.install_id,b)
                if any(c.shape(e)not in c.ids for e in b):
                    miss+=len(b);fallback=len(gzip.compress(project_source(c.project,inst.install_id,b,True),1,mtime=0))
                    for size in dictionaries:totals[str(size)]+=fallback;base_totals[str(size)]+=fallback
                    continue
                start=time.perf_counter_ns();base=raw_encode(c,a,inst.install_id,b,False,True,True)
                packed,used=cross7.rewrite(base,c,b);elapsed=(time.perf_counter_ns()-start)/1e6
                restored,_=cross7.rewrite(packed,c,b,cross_input=True)
                assert restored==base; modes.update(used)
                if len(b)==100:times.append(elapsed)
                for size,d in dictionaries.items():
                    total,comp=body_size(packed,len(b),compressors[size]);totals[str(size)]+=total
                    assert z.ZstdDecompressor(dict_data=d).decompress(comp)==packed
                    base_totals[str(size)]+=body_size(base,len(b),old[size])[0]
        expected=next(r for r in baseline if r['variant']==variant and r['model']==model)
        assert all(base_totals[str(s)]==expected['bytes'][f'dict{s//1024}']for s in dictionaries)
        row={'variant':variant,'events':n,'fallback_events':miss,'logical_strings':logical,
             'estimated_frame_bytes':dict(totals),'estimated_frame_B_event':{k:v/n for k,v in totals.items()},
             'baseline_bytes':dict(base_totals),'baseline_B_event':{k:v/n for k,v in base_totals.items()},
             'mode_column_counts':dict(modes),'max_previous_signed_columns':cross7.MAX_REFS,
             'python_base_pack_and_transform100_ms':{'p50':statistics.median(times),'p95':sorted(times)[int(.95*(len(times)-1))]},
             'dictionary_sha256':{str(size):hashlib.sha256(d.as_bytes()).hexdigest()for size,d in dictionaries.items()},
             'scope':'Experimental raw columns; header+CRC byte allowance only. Not negotiated M7/native/Unity/full SDK. Excludes setup/HTTP/retry; excludes original event UUID.'}
        results.append(row);(ROOT/'results/cross-benchmark.json').write_text(json.dumps(results,indent=2));print(json.dumps(row),flush=True)
if __name__=='__main__':run()
