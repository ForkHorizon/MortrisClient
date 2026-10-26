"""Matched train/holdout ablations for generic string and metadata tables."""
from collections import Counter
import gzip,hashlib,json,time,statistics
from support7 import ROOT,z,canonical_source,project_source,v6
from transport7 import Catalog,Aliases,shape,raw_encode,encode,decode
from game_cleanup import cleaned
from real_data import load

MODELS={'strings':{'string_model':True},'metadata':{'metadata_model':True},'combined':{'string_model':True,'metadata_model':True},'logical_strings':{'string_model':True}}

def run():
    train,test=load();report=[]
    for variant in ('all_clean','raw'):
        tr=cleaned(train,migrate_interactions=True)if variant=='all_clean'else train
        te=cleaned(test,migrate_interactions=True)if variant=='all_clean'else test
        models=MODELS if variant=='all_clean'else {k:MODELS[k]for k in ('combined','logical_strings')}
        for name,opts in models.items():
            c=Catalog.train('puzzle_gravity_test',tr,logical_strings=name=='logical_strings')
            samples=[]
            for inst,bs in tr:
                a=Aliases(bytes(8))
                for b in bs:
                    a.register(inst.install_id,b);samples.append(raw_encode(c,a,inst.install_id,b,False,True,**opts))
            dictionaries={size:z.train_dictionary(size,samples,level=1)for size in (16384,32768)}
            for size,d in dictionaries.items():(ROOT/'results/private'/f'tables-{variant}-{name}-{size}.dict').write_bytes(d.as_bytes())
            totals=Counter();n=miss=0;times=[]
            for inst,bs in te:
                a=Aliases(bytes(8))
                for b in bs:
                    n+=len(b);a.register(inst.install_id,b)
                    modes=[('dict16',dictionaries[16384],False),('dict32',dictionaries[32768],False)]
                    if name in ('combined','logical_strings'):modes.append(('full_ids_dict16',dictionaries[16384],True))
                    if any(c.shape(e)not in c.ids for e in b):
                        miss+=len(b);fallback=len(gzip.compress(project_source(c.project,inst.install_id,b,True),1,mtime=0))
                        for mode,_,_ in modes:totals[mode]+=fallback
                        continue
                    for mode,d,full in modes:
                        start=time.perf_counter_ns();f=encode(c,a,inst.install_id,b,d,full,True,**opts);elapsed=(time.perf_counter_ns()-start)/1e6
                        o,ev=decode(c,a,f,d,authorized_project=c.project,authorized_origin=inst.install_id)
                        assert canonical_source(o,ev,full)==canonical_source(o,b,full)
                        totals[mode]+=len(f)
                        if mode=='dict32'and len(b)==100:times.append(elapsed)
            row={'variant':variant,'model':name,'options':opts,'logical_strings':c.logical_strings,'catalog_bytes':len(c.data),'catalog_shapes':len(c.shapes),'events':n,'fallback_events':miss,'bytes':dict(totals),'B_event':{k:v/n for k,v in totals.items()},
                 'python_host_encode100_ms':{'p50':statistics.median(times),'p95':sorted(times)[int(.95*(len(times)-1))]},
                 'dictionary_sha256':{str(size):hashlib.sha256(d.as_bytes()).hexdigest()for size,d in dictionaries.items()},
                 'CSharp_Go_Unity':'SEPARATE_STAGE_EVIDENCE; METADATA_MODEL_NOT_PORTED'}
            report.append(row);(ROOT/'results/tables-benchmark.json').write_text(json.dumps(report,indent=2));print(json.dumps(row),flush=True)
if __name__=='__main__':run()
