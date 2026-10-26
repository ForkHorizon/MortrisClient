from support7 import canonical_source
"""Independent training/holdout, exact roundtrips, paid setup, frozen baselines."""
import argparse, gzip, hashlib, json, platform, statistics, time
from support7 import ROOT, v6, core, wire, make, rebatch, drift, z
from transport7 import Catalog, Aliases, encode, decode, raw_encode, shape
from game_cleanup import cleaned
from framing import pack, unpack

RESULTS = ROOT / 'results'

def dataset(profile, seed, installs):
    return drift(seed, installs, 600) if profile == 'drift' else rebatch(make(profile, seed, installs), 100)

def samples(catalog, ds, preserve_ids=False):
    out = []
    for inst, batches in ds:
        aliases = Aliases(bytes(8))
        for batch in batches:
            aliases.register(inst.install_id, batch)
            out.append(raw_encode(catalog, aliases, inst.install_id, batch, preserve_ids))
    return out

def run(profile):
    train = dataset(profile, 202, 18)
    catalog = Catalog.train(profile, train)
    (RESULTS / f'catalog-{profile}.json').write_bytes(catalog.data)
    train_raw = samples(catalog, train)
    dictionaries = {size: z.train_dictionary(size, train_raw, level=1) for size in (16384, 32768)}
    for size, dictionary in dictionaries.items():
        (RESULTS / f'dict-{profile}-{size}.bin').write_bytes(dictionary.as_bytes())
    v6schema = v6.Schema.train(train)
    v6samples = []
    for inst, bs in train:
        a = Aliases(bytes(8))
        for b in bs:
            a.register(inst.install_id,b)
            v6samples.append(v6.encode_raw(v6schema,a,inst.install_id,b))
    v6dict = z.train_dictionary(16384,v6samples,level=1)
    v4dict = z.train_dictionary(65536,[core.encode(i,b,trailer=True)[0] for i,bs in train for b in bs],level=19)
    output = {'profile':profile,'training_seed':202,'training_samples':len(train_raw),
              'training_raw_bytes':sum(map(len,train_raw)),'catalog_bytes':len(catalog.data),
              'catalog_sha256':hashlib.sha256(catalog.data).hexdigest(),'rows':[]}
    for seed in (101,1729,2601):
        ds = dataset(profile,seed,6)
        # Historical generators do not contain the actual game's CSV/hash relation.
        # Safe cleanup retains all non-derivable hashes and missing interaction indices.
        for variant, current in [('raw',ds),('safe_clean',cleaned(ds,migrate_interactions=True))]:
            sc = Catalog.train(profile, cleaned(train,migrate_interactions=True)) if variant=='safe_clean' else catalog
            sd = {size:z.train_dictionary(size,samples(sc,cleaned(train,migrate_interactions=True)),level=1) for size in dictionaries} if variant=='safe_clean' else dictionaries
            matched_train = train if variant=='raw' else cleaned(train,migrate_interactions=True)
            matched_v6_schema = v6schema if variant=='raw' else v6.Schema.train(matched_train)
            matched_v6_samples = []
            if variant != 'raw':
                for mi, mbs in matched_train:
                    ma=Aliases(bytes(8))
                    for mb in mbs:
                        ma.register(mi.install_id,mb)
                        matched_v6_samples.append(v6.encode_raw(matched_v6_schema,ma,mi.install_id,mb))
            matched_v6_dict = v6dict if variant=='raw' else z.train_dictionary(16384,matched_v6_samples,level=1)
            matched_v4_dict = v4dict if variant=='raw' else z.train_dictionary(65536,[core.encode(i,b,trailer=True)[0] for i,bs in matched_train for b in bs],level=19)
            totals = {k:0 for k in ('v1_json','v1_gzip1','v4_zstd19','v6_zstd1','v6_dict16', 'v7_nodict','v7_dict16','v7_dict32','v7_full_ids_dict16')}
            timings=[]; n=nb=setup=misses=0; digest=hashlib.sha256()
            for inst,bs in current:
                a,server = Aliases(bytes(8)),Aliases(bytes(8))
                for b in bs:
                    src=v6.render(inst.install_id,b,True)
                    digest.update(len(src).to_bytes(8,'little'));digest.update(src)
                    n+=len(b);nb+=1
                    totals['v1_json']+=len(src);totals['v1_gzip1']+=len(gzip.compress(src,1,mtime=0))
                    payload=a.register(inst.install_id,b)
                    if payload:server.accept(payload);setup+=len(payload)+8+len(v6.u(len(a.records)))
                    totals['v6_zstd1']+=len(v6.encode(matched_v6_schema,a,inst.install_id,b))
                    v6raw=v6.encode_raw(matched_v6_schema,a,inst.install_id,b)
                    totals['v6_dict16']+=len(z.ZstdCompressor(level=1,dict_data=matched_v6_dict).compress(v6raw))+24+len(v6.u(len(b)))+len(v6.u(len(v6raw)))+8
                    raw,tail=core.encode(inst,b,trailer=True)
                    frame=pack(raw,tail,len(b),matched_v4_dict,1,19)
                    _,rr,tt,_=unpack(frame,{1:matched_v4_dict});_,ev=core.decode(rr,tt)
                    assert v6.render(inst.install_id,ev)==v6.render(inst.install_id,b)
                    totals['v4_zstd19']+=len(frame)
                    modes=[('v7_nodict',None,False),('v7_dict16',sd[16384],False),('v7_dict32',sd[32768],False),('v7_full_ids_dict16',sd[16384],True)]
                    if any(shape(e) not in sc.ids for e in b):
                        misses+=len(b)
                        for mode,_,_ in modes:totals[mode]+=len(gzip.compress(src,1,mtime=0))
                        continue
                    for mode,d,full in modes:
                        start=time.perf_counter_ns();f=encode(sc,a,inst.install_id,b,d,full);elapsed=(time.perf_counter_ns()-start)/1e6
                        origin,ev=decode(sc,server,f,d,authorized_project=profile,authorized_origin=inst.install_id)
                        assert canonical_source(origin,ev,full)==canonical_source(inst.install_id,b,full)
                        totals[mode]+=len(f)
                        if mode=='v7_dict16' and len(b)==100:timings.append(elapsed)
            output['rows'].append({'seed':seed,'variant':variant,'events':n,'batches':nb,'sha256':digest.hexdigest(),
                'bytes':totals,'B_event':{k:v/n for k,v in totals.items()},'alias_setup_bytes':setup,'fallback_events':misses,
                'dict16_setup_inclusive_B_event':(totals['v7_dict16']+setup+len(sc.data)+16384)/n,
                'python_host_encode100_ms':{'p50':statistics.median(timings),'p95':sorted(timings)[int(.95*(len(timings)-1))]} if timings else None})
            print(profile,seed,variant,{k:round(v/n,3) for k,v in totals.items()},flush=True)
        (RESULTS/f'bench-{profile}.json').write_text(json.dumps(output,indent=2))
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('profiles',nargs='*',default=['base','rich','alt','drift']);args=parser.parse_args()
    for profile in args.profiles:run(profile)
    (RESULTS/'environment.json').write_text(json.dumps({'python':platform.python_version(),'platform':platform.platform(),'zstd':z.ZSTD_VERSION,'zstandard':z.__version__,'phone_measurements':False},indent=2))
