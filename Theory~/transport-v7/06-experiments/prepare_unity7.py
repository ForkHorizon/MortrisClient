"""Generate an isolated Unity project and uniform DTO fixtures; never alter Puzzle/SDK."""
import json,shutil,struct
from pathlib import Path
from support7 import ROOT

PROJECT=ROOT/'results/private/unity-player'
def run():
    for folder in ('Assets/Editor','Assets/StreamingAssets','Packages','ProjectSettings'):(PROJECT/folder).mkdir(parents=True,exist_ok=True)
    for name in ('Harness.cs','PlayerBootstrap.cs'):shutil.copyfile(ROOT/'unity'/name,PROJECT/'Assets'/name)
    shutil.copyfile(ROOT/'unity/EditorBootstrap.cs',PROJECT/'Assets/Editor/EditorBootstrap.cs')
    shutil.copyfile(ROOT/'native/Columns.cs',PROJECT/'Assets/Columns.cs')
    (PROJECT/'Assets/csc.rsp').write_text('-unsafe\n')
    (PROJECT/'Packages/manifest.json').write_text(json.dumps({'dependencies':{'com.unity.modules.jsonserialize':'1.0.0','com.unity.modules.androidjni':'1.0.0'}}))
    (PROJECT/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.3.16f1\n')
    fixtures=[]
    for directory in (ROOT/'fixtures',ROOT/'results/private'):
        for source in sorted(directory.glob('*.raw')):
            jp=source.with_suffix('.json');dp=source.with_suffix('.dict')
            if not jp.exists()or not dp.exists():continue
            f=json.loads(jp.read_text());types=f['types']
            for row in f['rows']:
                row['id']=list(bytes.fromhex(row['id']));values=[]
                for c,v in zip(row['columns'],row['values']):
                    t=types[c];out={}
                    if t==0:out={'i':str(v)}
                    elif t==10:out={'u':str(v)}
                    elif t==2:out={'i':str(int(v))}
                    elif t in (3,4):out={'d':struct.pack('>d',v).hex()}
                    elif t!=7:out={'s':v}
                    values.append(out)
                row['values']=values
            label=source.stem;fixtures.append(label)
            (PROJECT/'Assets/StreamingAssets'/f'{label}.json').write_text(json.dumps(f,ensure_ascii=True,separators=(',',':')))
            shutil.copyfile(dp,PROJECT/'Assets/StreamingAssets'/f'{label}.dict')
    expected=12+(4 if (ROOT/'results/native-tables.json').exists()else 0)
    assert len(fixtures)==expected,len(fixtures)
    (PROJECT/'Assets/StreamingAssets/manifest.json').write_text(json.dumps({'fixtures':fixtures}))
    print(PROJECT)
if __name__=='__main__':run()
