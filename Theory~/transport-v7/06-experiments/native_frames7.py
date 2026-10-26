"""Full C# M7 packets -> independent Python decode, plus real-corpus conformance.
Private typed inputs are prepared before measurement; no SDK/production calls.
"""
import copy,gzip,hashlib,json,os,random,struct,subprocess,uuid,zlib
from pathlib import Path
from decimal import Decimal
from collections import Counter
from support7 import ROOT,z,v6,Reader,make,rebatch,canonical_source,project_source
from transport7 import Catalog,Aliases,decode
from native_check7 import input_data
from real_data import load
from game_cleanup import cleaned

PRIVATE=ROOT/'results/private/frames'
EPOCH=bytes.fromhex('0102030405060708')
GO_CASES=[]

def export_go_case(c,a,inst,b,d,ids,packet):
    assets=PRIVATE/'go-assets';assets.mkdir(exist_ok=True)
    def asset(data,suffix):
        path=assets/(hashlib.sha256(data).hexdigest()+suffix)
        if path.exists():assert path.read_bytes()==data
        else:path.write_bytes(data)
        return str(path)
    catalog=asset(c.data,'.catalog.json')
    aliases=asset(json.dumps({'epoch':a.epoch.hex(),'records':a.records},ensure_ascii=True,separators=(',',':')).encode(),'.aliases.json')
    dictionary=asset(d.as_bytes()if d else b'','.dict')
    expected=PRIVATE/'go-expected'/(packet.stem+'.v1.json');expected.parent.mkdir(exist_ok=True)
    expected.write_bytes(project_source(c.project,inst.install_id,b,ids))
    GO_CASES.append({'name':packet.stem,'catalog':catalog,'aliases':aliases,'dictionary':dictionary,
                     'project':c.project,'origin':inst.install_id,'frame':str(packet),'expected':str(expected),
                     'shapes':[c.ids[c.shape(e)]for e in b]})

def execute(name,c,dictionary,jobs,ids,numeric,strings,iterations=1,warmup=1):
    path=PRIVATE/(name+'.manifest.json')
    path.write_text(json.dumps({'dictionary':str(dictionary),'catalog_id':c.id.hex(),'epoch':EPOCH.hex(),
                               'preserve_ids':ids,'integer_model':numeric,'string_model':strings,
                               'iterations':iterations,'warmup':warmup,'jobs':jobs}))
    env=dict(os.environ,DYLD_LIBRARY_PATH='/opt/homebrew/opt/zstd/lib')
    proc=subprocess.run(['dotnet',str(ROOT/'native/bin/Release/net10.0/Frames.dll'),str(path)],env=env,text=True,capture_output=True,check=True)
    rows=[json.loads(line)for line in proc.stdout.splitlines()]
    assert len(rows)==len(jobs)and all(r['gc_bytes']==0 and r['allocation_control_bytes']>=4096 for r in rows)
    for row,job in zip(rows,jobs):assert row['success']==job.get('expected_success',True)
    return rows

def check(frame,c,a,inst,b,d,ids,packet=None):
    origin,events=decode(c,a,frame,d,authorized_project=c.project,authorized_origin=inst.install_id)
    assert canonical_source(origin,events,ids)==canonical_source(inst.install_id,b,ids)
    if packet is not None:export_go_case(c,a,inst,b,d,ids,packet)

def job(folder,label,data,**extra):
    folder.mkdir(parents=True,exist_ok=True);inp=folder/(label+'.json');out=folder/(label+'.m7')
    inp.write_text(json.dumps(data,ensure_ascii=True,separators=(',',':')))
    return dict(name=label,input=str(inp),output=str(out),**extra)

def tests():
    ds=rebatch(make('base',3001,1),100);inst,bs=ds[0];batch=copy.deepcopy(bs[0]);rng=random.Random(3002)
    for i,e in enumerate(batch):
        e['properties']={'counter':i,'wide':(-(1<<63)if i%2 else(1<<63)-1),'unsigned':(1<<64)-1,
                         'float':[-0.0,.005,1.25][i%3],'flag':bool(i%2),'null':None,'text':'文字🙂'+str(i),
                         'uuid':str(uuid.UUID(int=rng.getrandbits(128))),'hex':f'{rng.getrandbits(128):032x}',
                         'decimal':Decimal('-0.000')if i%2 else Decimal('1.2300')}
    c=Catalog.train('frame_protocol_test',[(inst,[batch])]);a=Aliases(EPOCH);a.register(inst.install_id,batch)
    dp=ROOT/'fixtures/native-base100.dict';d=z.ZstdCompressionDict(dp.read_bytes());rows=[]
    for flags in range(8):
        ids,numeric,strings=bool(flags&1),bool(flags&2),bool(flags&4)
        data=input_data(inst,batch,c,a,ids,numeric,strings)
        small=job(PRIVATE/'tests',f'flags-{flags}-small',data,capacity=38,expected_success=False)
        valid=job(PRIVATE/'tests',f'flags-{flags}',data)
        measured=execute(f'flags-{flags}',c,dp,[small,valid],ids,numeric,strings,1000,100)
        frame=Path(valid['output']).read_bytes();assert frame[2]==flags and frame[3]==1
        check(frame,c,a,inst,batch,d,ids,Path(valid['output']))
        measured[-1]['python_full_packet_roundtrip']=True;rows+=measured
        # CRC corruption and asset/auth mismatches are checked on native packets, not synthetic Python frames.
        for broken in (frame[:-1]+bytes([frame[-1]^1]),frame+b'\0'):
            try:decode(c,a,broken,d,authorized_project=c.project,authorized_origin=inst.install_id)
            except (ValueError,z.ZstdError):pass
            else:raise AssertionError('accepted corruption')
        for project,origin in (('other_project',inst.install_id),(c.project,'other_origin')):
            try:decode(c,a,frame,d,authorized_project=project,authorized_origin=origin)
            except (ValueError,z.ZstdError):pass
            else:raise AssertionError('accepted wrong authorization')
        malformed=[]
        for index in (2,3,4,12,20,28,29):
            payload=bytearray(frame[:-4]);payload[index]=payload[index]|8 if index==2 else 2 if index==3 else 0 if index==28 else payload[index]^1
            malformed.append(bytes(payload))
        malformed.extend((frame[:28]+b'\xe4\x00'+frame[29:-4],frame[:28]+v6.u(501)+frame[29:-4],frame[:-4]+b'\0'))
        for payload in malformed:
            broken=payload+struct.pack('<I',zlib.crc32(payload))
            try:decode(c,a,broken,d,authorized_project=c.project,authorized_origin=inst.install_id)
            except (ValueError,z.ZstdError):pass
            else:raise AssertionError('accepted CRC-valid malformed header/body')
        measured[-1].update(flags=flags,crc_invalid_rejections=2,authorization_rejections=2,crc_valid_malformed_rejections=len(malformed))
    tiny=copy.deepcopy(batch[:1]);tiny[0]['properties']={}
    tc=Catalog.train('frame_tiny',[(inst,[tiny])]);ta=Aliases(EPOCH);ta.register(inst.install_id,tiny)
    empty=PRIVATE/'empty.dict';empty.write_bytes(b'')
    tj=job(PRIVATE/'tests','raw-no-dictionary',input_data(inst,tiny,tc,ta,True))
    tr=execute('tiny',tc,empty,[tj],True,False,False,1000,100)
    frame=Path(tj['output']).read_bytes();assert frame[3]==0 and frame[20:28]==bytes(8)
    check(frame,tc,ta,inst,tiny,None,True,Path(tj['output']));tr[0].update(python_full_packet_roundtrip=True,frame_compression=0,dictionary_bytes=0);rows+=tr
    large=[]
    for i in range(500):
        e=copy.deepcopy(batch[0]);e.update(sequence=i+1,ts=e['ts']+i*20,session_elapsed_ms=e['session_elapsed_ms']+i*20,event_id=str(uuid.UUID(int=i+7000)),
                                         properties={'counter':i,'text':('é'if i%2 else'ê')+'🙂'*230+str(i)})
        large.append(e)
    lc=Catalog.train('frame_large',[(inst,[large])]);la=Aliases(EPOCH);la.register(inst.install_id,large)
    lj=job(PRIVATE/'tests','large-compressed',input_data(inst,large,lc,la,True,True,True))
    lr=execute('large',lc,dp,[lj],True,True,True,1000,100)
    frame=Path(lj['output']).read_bytes();assert frame[3]==1 and len(frame)<262144
    header=Reader(frame);header.take(28);assert header.count(500)==500
    raw_size=header.count(2097152);assert raw_size>262144
    check(frame,lc,la,inst,large,d,True,Path(lj['output']));lr[0].update(python_full_packet_roundtrip=True,frame_compression=1,raw_bytes=raw_size);rows+=lr
    (ROOT/'results/native-frames-tests.json').write_text(json.dumps(rows,indent=2))
    return rows

def corpus():
    train,test=load();report=[]
    baseline=json.loads((ROOT/'results/tables-benchmark.json').read_text())
    for variant in ('raw','all_clean'):
        tr=train if variant=='raw'else cleaned(train,migrate_interactions=True)
        te=test if variant=='raw'else cleaned(test,migrate_interactions=True)
        logical=variant=='raw';model='logical_strings'if logical else'strings'
        c=Catalog.train('puzzle_gravity_test',tr,logical_strings=logical)
        (PRIVATE/(variant+'-catalog.json')).write_bytes(c.data)
        dp=ROOT/'results/private'/f'tables-{variant}-{model}-32768.dict';d=z.ZstdCompressionDict(dp.read_bytes())
        jobs=[];expected=[];events=miss=fallback=0
        for inst,bs in te:
            a=Aliases(EPOCH)
            for b in bs:
                events+=len(b);a.register(inst.install_id,b)
                if any(c.shape(e)not in c.ids for e in b):
                    miss+=len(b);fallback+=len(gzip.compress(project_source(c.project,inst.install_id,b,True),1,mtime=0));continue
                label=f'{variant}-{len(jobs):04d}'
                jobs.append(job(PRIVATE/variant,label,input_data(inst,b,c,a,False,True,True)))
                expected.append((inst,b,a))
        measured=execute('corpus-'+variant,c,dp,jobs,False,True,True)
        total=fallback;compression=Counter()
        for item,(inst,b,a),metric in zip(jobs,expected,measured):
            frame=Path(item['output']).read_bytes();assert metric['frame_bytes']==len(frame)
            check(frame,c,a,inst,b,d,False,Path(item['output']));total+=len(frame);compression[frame[3]]+=1
        old=next(r for r in baseline if r['variant']==variant and r['model']==model)
        row={'variant':variant,'events':events,'native_frames':len(jobs),'native_events':events-miss,'fallback_events':miss,'fallback_bytes':fallback,
             'bytes':total,'B_event':total/events,'python_baseline_bytes':old['bytes']['dict32'],'byte_delta_vs_python':total-old['bytes']['dict32'],
             'all_native_packets_python_roundtrip':True,'all_native_pack_gc_bytes':0,'frame_compression_counts':dict(compression),
             'catalog_id':c.id.hex(),'scope':'Real C# full M7 packets (columns+zstd+header+CRC); typed inputs prepared by Python. Not SDK ingress/delivery/Go server/Unity frame proof. Legacy IDs and conditional game migration.'}
        report.append(row);(ROOT/'results/native-frames-corpus.json').write_text(json.dumps(report,indent=2));print(json.dumps(row),flush=True)
    return report

if __name__=='__main__':
    PRIVATE.mkdir(parents=True,exist_ok=True);tests();corpus()
    (PRIVATE/'go-cases.json').write_text(json.dumps(GO_CASES))
