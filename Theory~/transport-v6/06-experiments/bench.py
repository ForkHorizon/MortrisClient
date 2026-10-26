"""Frozen train202, test101/holdout1729/drift1733. Every V6 body is decoded.
Previous V4/V5 full-matrix numbers independently rerun and matched after corpus SHA verification.
"""
import argparse, gzip, hashlib, json, platform, sys, time
from codec import *
from support import ROOT, V5, make, rebatch, drift
from model import Model
import frame_v5
from framing import pack

RESULTS = ROOT/'results'

def dataset(profile, seed, installs):
    return drift(seed, installs, 600) if profile == 'drift' else rebatch(make(profile, seed, installs), 100)

def run(profile):
    training = dataset(profile, 202, 12 if profile=='drift' else 18)
    schema = Schema.train(training)
    (RESULTS/f'schema-{profile}.json').write_bytes(schema.data)
    schema_frame = z.ZstdCompressor(level=1).compress(schema.data)
    prior = Model.restore((V5/'results'/f'prior14-{profile}.bin').read_bytes())
    v4dict = z.train_dictionary(65536, [core.encode(i,b,trailer=True)[0] for i,bs in training for b in bs], level=19)
    old = json.loads((V5/'results'/f'bench-{profile}.json').read_text())
    manifest = json.loads((V5/'results/corpus-manifest.json').read_text())
    output={'profile':profile,'schema_bytes':len(schema.data),'schema_negotiation_bytes':len(schema_frame)+8,'schema_id':schema.id.hex(),'shapes':len(schema.shapes),'rows':{}}
    for label, seed in [('test101',101),('holdout1729',1733 if profile=='drift' else 1729)]:
        # Historical drift808 is retained to compare the exact existing V5 corpus.
        actual_seed=808 if profile=='drift' and label=='test101' else seed
        ds=dataset(profile,actual_seed,4 if profile=='drift' else 6)
        historical='historical' if label=='test101' else 'fresh_holdout'
        h=hashlib.sha256(); n=nb=jsonbytes=fulljson=gzipbytes=0
        modes={m:0 for m in ('columnar_raw','zstd1','zstd3','replay_zstd1','strict_V1_ids_zstd1','replay_strict_ids','explicit_masks','dynamic_schema','batch_local_aliases','lz4','replay_lz4')}
        clients={m:Aliases() for m in modes}; servers={m:Aliases() for m in modes}
        registrations={m:0 for m in modes}; acknowledgments={m:0 for m in modes}
        exts=hashes=floats=exact2=hash_binary=0
        v4bytes=v5bytes=nohashbytes=sessions=0
        fields={}; timing=[]; v5checks=[]
        for inst, batches in ds:
            sessions += len({e['session_id'] for b in batches for e in b})
            for b in batches:
                source=render(inst.install_id,b)
                h.update(len(source).to_bytes(8,'little'));h.update(source)
                n+=len(b);nb+=1;jsonbytes+=len(source);fulljson+=len(render(inst.install_id,b,True));gzipbytes+=len(gzip.compress(wire.v1_json(inst,b),1,mtime=0))
                for e in b:
                    for k,v in e['properties'].items():
                        fields.setdefault('properties.'+k,[0,0])[0]+=len(wire.jdump(k).encode())+1+len(wire.jdump(v).encode('utf-8',errors='backslashreplace'))
                        fields['properties.'+k][1]+=1
                        if k=='placed_state_hash':hashes+=1;hash_binary+=len(v)//2
                        if type(v) is float:
                            floats+=1
                            fmt = '<f' if core._is_f32(v) else '<d'
                            if math.isfinite(v*100) and struct.pack(fmt,round(v*100)/100)==struct.pack(fmt,v):exact2+=1
                    for k in ('session_id','name',*wire.DEVICE_KEYS,'sequence','ts','session_elapsed_ms','event_id'):
                        fields.setdefault(k,[0,0])[0]+=len(wire.jdump(k))+1+len(wire.jdump(e[k]));fields[k][1]+=1
                    exts+=int(shape(e) not in schema.ids)
                for m in modes:
                    sc=Schema([]) if m=='dynamic_schema' else schema
                    if m=='batch_local_aliases':clients[m]=Aliases();servers[m]=Aliases()
                    payload=clients[m].register(inst.install_id,b)
                    if payload:
                        servers[m].accept(payload)
                        registrations[m]+=len(payload)
                        # Concrete reply: cumulative next slot (varint) + 8-byte epoch.
                        acknowledgments[m]+=8+len(u(len(clients[m].records)))
                    opts=dict(replay=m in ('replay_zstd1','replay_strict_ids','replay_lz4'),preserve_ids=m in ('strict_V1_ids_zstd1','replay_strict_ids'),masks=m=='explicit_masks',lz4=m in ('lz4','replay_lz4'),level=3 if m=='zstd3' else 1)
                    if m=='columnar_raw':
                        raw=encode_raw(sc,clients[m],inst.install_id,b)
                        origin, ev=decode_raw(sc,servers[m],raw,len(b),0)
                        assert render(origin,ev)==source
                        modes[m]+=len(raw)+24+len(u(len(b)))+len(u(len(raw)))
                    else:
                        f=encode(sc,clients[m],inst.install_id,b,**opts)
                        got=decode(sc,servers[m],f,authorized_origin=inst.install_id)
                        assert got==render(inst.install_id,b,opts['preserve_ids'])
                        modes[m]+=len(f)
                if len(timing)<12:
                    a=clients['zstd1'];f=encode(schema,a,inst.install_id,b)
                    start=time.perf_counter_ns();encode(schema,a,inst.install_id,b);enc=(time.perf_counter_ns()-start)/1e6
                    start=time.perf_counter_ns();decode(schema,a,f,authorized_origin=inst.install_id);dec=(time.perf_counter_ns()-start)/1e6
                    timing.append({'n':len(b),'encode_ms':enc,'decode_ms':dec})
                start=time.perf_counter_ns();f,_=frame_v5.encode(prior,inst.install_id,b);enc=(time.perf_counter_ns()-start)/1e6
                start=time.perf_counter_ns();restored,_=frame_v5.decode(prior,f);dec=(time.perf_counter_ns()-start)/1e6
                assert restored==source
                v5bytes+=len(f)
                if len(v5checks)<3:
                    v5checks.append({'events':len(b),'frame_bytes':len(f),'encode_ms':enc,'decode_ms':dec})
                raw,tail=core.encode(inst,b,trailer=True)
                v4=pack(raw,tail,len(b),v4dict,1,19)
                from framing import unpack
                _,restored_raw,restored_tail,_=unpack(v4,{1:v4dict})
                _,v4events=core.decode(restored_raw,restored_tail)
                assert render(inst.install_id,v4events)==source
                v4bytes+=len(v4)
                nohash=[dict(e,properties={k:v for k,v in e['properties'].items() if k!='placed_state_hash'}) for e in b]
                nohashbytes+=len(encode(schema,clients['zstd1'],inst.install_id,nohash))
        original_key='historical' if label=='test101' else 'fresh_holdout'
        expected=manifest[profile][original_key]
        assert h.hexdigest()==expected['source_length_prefixed_sha256'], (profile,label,'corpus mismatch')
        assert n==expected['events'] and nb==expected['batches']
        assert v5bytes==old['rows'][historical]['stateless']['bytes']
        assert abs(v4bytes/n-old['rows'][historical]['V4_B_per_event'])<1e-12
        row={'seed':actual_seed,'events':n,'batches':nb,'corpus_sha256':h.hexdigest(),'V1_full_json_B_event':fulljson/n,'V1_full_gzip1_B_event':gzipbytes/n,'legacy_source_json_B_event':jsonbytes/n,'V4_zstd19_B_event':old['rows'][historical]['V4_B_per_event'],'V5_stateless_B_event':old['rows'][historical]['stateless']['B_per_event'],'V4_V5_evidence':'frozen results with identical length-prefixed source SHA; V5 first3 batches rerun','V6':{},'new_shape_events':exts,'hash_occurrences':hashes,'hash_binary_naive_B_event':hash_binary/n,'floats':floats,'exact_two_decimals':exact2,'python_timings':timing,'V5_rerun':v5checks,'field_json_bytes':{k:{'bytes':v[0],'occurrences':v[1],'B_event':v[0]/n} for k,v in sorted(fields.items())}}
        for m,total in modes.items():
            setup=registrations[m]+acknowledgments[m]
            row['V6'][m]={'body_bytes':total,'body_B_event':total/n,'alias_request_bytes':registrations[m],'alias_response_bytes':acknowledgments[m],'with_alias_setup_B_event':(total+setup)/n,'with_dynamic_schema_and_alias_B_event':(total+setup+((len(schema_frame)+8)*len(ds) if m!='dynamic_schema' else 0))/n}
            row['V6'][m]['with_session_schema_and_alias_B_event']=(total+setup+(len(schema_frame)+8)*sessions)/n
        row.update(V4_measured_bytes=v4bytes,V5_measured_bytes=v5bytes,V4_V5_evidence='full independent encode/decode rerun; exact source SHA and historical byte totals matched',sessions=sessions)
        row['hash_omission_nonlossless_B_event']=nohashbytes/n
        output['rows'][label]=row
        (RESULTS/f'bench-{profile}.json').write_text(json.dumps(output,indent=2))
        print(profile,label,n,{m:round(v['body_B_event'],3) for m,v in row['V6'].items()},flush=True)
    return output

if __name__=='__main__':
    RESULTS.mkdir(exist_ok=True)
    parser=argparse.ArgumentParser();parser.add_argument('profiles',nargs='*',default=['base','rich','alt','drift']);args=parser.parse_args()
    for p in args.profiles:run(p)
    (RESULTS/'environment.json').write_text(json.dumps({'python':sys.version,'platform':platform.platform(),'machine':platform.machine(),'zstandard':z.__version__,'zstd':z.ZSTD_VERSION,'training_seed':202,'phone_measurements':False},indent=2))
