from support7 import canonical_source
"""C# host typed columns+zstd, paired with Python decoder; never phone evidence."""
import json, os, subprocess, uuid
from decimal import Decimal
from support7 import ROOT,v6,make,rebatch,z
from transport7 import Catalog,Aliases,shape,raw_decode,raw_encode

def input_data(inst,b,catalog,a,preserve_ids=True,integer_model=False,string_model=False):
    columns={};types=[];rows=[];sessions={}
    for e in b:
        keys=[];values=[]
        for k,t in catalog.shape(e)[1]:
            col=(k,t)
            if col not in columns:columns[col]=len(columns);types.append(t)
            keys.append(columns[col]);value=e['properties'][k];values.append(str(value) if type(value)is Decimal else value)
        sessions.setdefault(e['session_id'],len(sessions))
        rows.append({'sequence':e['sequence'],'time':e['ts'],'elapsed':e['session_elapsed_ms'],
                     'shape':catalog.ids[catalog.shape(e)],'context':a.ids[(inst.install_id,*(e[k] for k in v6.CTX))],
                     'session':sessions[e['session_id']],'id':uuid.UUID(e['event_id']).hex,'columns':keys,'values':values})
    return {'types':types,'rows':rows,'preserve_ids':preserve_ids,'integer_model':integer_model,'string_model':string_model}

def fixture(name,inst,b,catalog,dictionary,integer_model=False,string_model=False):
    a=Aliases(bytes(8));a.register(inst.install_id,b)
    target=ROOT/'fixtures'/f'{name}.json';target.write_text(json.dumps(input_data(inst,b,catalog,a,True,integer_model,string_model),ensure_ascii=True))
    dp=ROOT/'fixtures'/f'{name}.dict';dp.write_bytes(dictionary.as_bytes())
    output=ROOT/'fixtures'/f'{name}.raw'
    env=dict(os.environ,DYLD_LIBRARY_PATH='/opt/homebrew/opt/zstd/lib')
    result=subprocess.run(['dotnet',str(ROOT/'native/bin/Release/net10.0/Columns.dll'),str(target),str(dp),str(output)],env=env,text=True,capture_output=True,check=True)
    origin,events=raw_decode(catalog,a,output.read_bytes(),len(b),True,integer_model,string_model)
    assert canonical_source(origin,events,True)==canonical_source(inst.install_id,b,True)
    row=json.loads(result.stdout);row['fixture']=name;row['python_roundtrip']=True
    if string_model:row['python_raw_parity']=output.read_bytes()==raw_encode(catalog,a,inst.install_id,b,True,integer_model,string_model)
    return row

def run():
    ds=rebatch(make('base',2601,1),100);inst,bs=ds[0];b=bs[0]
    c=Catalog.train('native_test',ds)
    from bench7 import samples
    d=z.train_dictionary(4096,samples(c,ds)*3,level=1)
    results=[fixture('native-base100',inst,b,c,d)]
    import copy
    edge=copy.deepcopy(b[:3])
    for i,e in enumerate(edge):e['properties']={'integer':[-(1<<63),(1<<63)-1,0][i],'unsigned':(1<<64)-1,'float':[-0.0,.005,1.25][i],'flag':bool(i%2),'null':None,'text':'遊戲é🙂','hex':'aabbcc','uuid':e['event_id'],'decimal':Decimal('1.2300')}
    ec=Catalog.train('native_edge',[(inst,[edge])])
    results.append(fixture('native-edges',inst,edge,ec,d))
    large=[]
    for i in range(500):
        e=copy.deepcopy(b[0]);e['sequence']=i+1;e['ts']+=i*20;e['session_elapsed_ms']+=i*20;e['event_id']=str(uuid.UUID(int=i+1));e['properties']={'counter':i,'flag':bool(i%2),'text':'遊戲é🙂'+str(i)};large.append(e)
    lc=Catalog.train('native500',[(inst,[large])])
    results.append(fixture('native-500',inst,large,lc,d))
    (ROOT/'results/native-csharp.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
if __name__=='__main__':run()
