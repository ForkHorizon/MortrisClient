"""Go decodes real C# packets from catalog/aliases only; Python compares typed source."""
import json,struct,subprocess,zlib
from decimal import Decimal
from pathlib import Path
from support7 import ROOT,core,v6

PRIVATE=ROOT/'results/private/frames'

def compare(case,output):
    got=json.loads(output.read_bytes(),parse_float=Decimal)
    source=json.loads(Path(case['expected']).read_bytes(),parse_float=Decimal)
    catalog=json.loads(Path(case['catalog']).read_bytes())
    native_input=json.loads(Path(case['frame']).with_suffix('.json').read_bytes())
    assert set(got)=={'project_id','origin_install','events'}
    assert got['project_id']==case['project']==source['project_id']and got['origin_install']==case['origin']==source['install_id']
    assert len(got['events'])==len(source['events'])==len(case['shapes'])
    for actual,expected,sid,row in zip(got['events'],source['events'],case['shapes'],native_input['rows']):
        assert set(actual)==set(expected)
        kinds=dict(catalog['shapes'][sid][1]);assert set(actual['properties'])==set(expected['properties'])==set(kinds)
        original=dict(zip(kinds,row['values']))
        for key,value in expected.items():
            if key!='properties':assert type(actual[key])is type(value)and actual[key]==value,(case['name'],key)
        for key,value in expected['properties'].items():
            other=actual['properties'][key];kind=kinds[key]
            if kind in (core.T_F32,core.T_F64):
                # V1's shortest-f32 formatter normalizes -0 to0; original typed input is the bit-level authority.
                fmt='<f'if kind==core.T_F32 else'<d'
                assert type(other)is Decimal and struct.pack(fmt,float(other))==struct.pack(fmt,float(original[key])),(case['name'],key)
            elif kind==core.T_NUMTEXT:
                assert type(other)is Decimal and other.as_tuple()==value.as_tuple(),(case['name'],key)
            else:assert type(other)is type(value)and other==value,(case['name'],key)

def run():
    cases=json.loads((PRIVATE/'go-cases.json').read_text());assert len(cases)==1316
    exe=ROOT/'results/private/go-columns-check'
    subprocess.run(['go','build','-o',str(exe),'.'],cwd=ROOT/'go',check=True)
    output=PRIVATE/'go-decoded';output.mkdir(exist_ok=True)
    negative=PRIVATE/'go-malformed';negative.mkdir(exist_ok=True)
    groups={};expected_outputs=[];invalid=0
    for case in cases:
        groupkey=tuple(case[k]for k in ('catalog','aliases','dictionary','project','origin'))
        group=groups.setdefault(groupkey,dict(zip(('catalog','aliases','dictionary','project','origin'),groupkey),jobs=[]))
        target=output/(case['name']+'.json')
        group['jobs'].append({'name':case['name'],'frame':case['frame'],'output':str(target)})
        expected_outputs.append((case,target))
        if not case['name'].startswith('flags-'):continue
        frame=Path(case['frame']).read_bytes();malformed=[]
        for index in (2,3,4,12,20,28,29):
            data=bytearray(frame[:-4]);data[index]=data[index]|8 if index==2 else 2 if index==3 else 0 if index==28 else data[index]^1
            malformed.append(bytes(data))
        malformed.extend((frame[:28]+b'\xe4\x00'+frame[29:-4],frame[:28]+v6.u(501)+frame[29:-4],frame[:-4]+b'\0'))
        broken=[data+struct.pack('<I',zlib.crc32(data))for data in malformed]
        broken.extend((frame[:-1]+bytes([frame[-1]^1]),frame+b'\0'))
        for i,data in enumerate(broken):
            name=f"{case['name']}-bad-{i}";path=negative/(name+'.m7');path.write_bytes(data)
            group['jobs'].append({'name':name,'frame':str(path),'expected_error':True});invalid+=1
        for kwargs in ({'project':'other_project'},{'origin':'00000000-0000-0000-0000-0000000000ff'}):
            group['jobs'].append(dict(name=case['name']+'-wrong-auth',frame=case['frame'],expected_error=True,**kwargs));invalid+=1
    manifest=PRIVATE/'go-frame-manifest.json';manifest.write_text(json.dumps({'groups':list(groups.values())}))
    proc=subprocess.run([str(exe),'--frame-manifest',str(manifest)],capture_output=True,text=True,check=True)
    result=json.loads(proc.stdout);assert result['decoded_packets']==len(cases)and result['rejected_packets']==invalid==112
    for case,path in expected_outputs:compare(case,path)
    result.update(all_source_typed_values_equal=True,signed_zero_and_decimal_lexemes_preserved=True,
                  runtime_inputs='catalog + registered aliases + dictionary + authenticated project/origin; no fixture rows/column hints',
                  scope='Offline Go full M7 decoder; no HTTP/persistence/ACK or production integration')
    (ROOT/'results/go-frames.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=='__main__':run()
