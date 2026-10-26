import json,subprocess
from support7 import ROOT,z

def run(numeric=False,tables=False):
    exe=ROOT/'results/private/go-columns-check'
    subprocess.run(['go','build','-o',str(exe),'.'],cwd=ROOT/'go',check=True)
    rows=[]
    for directory in (ROOT/'fixtures',ROOT/'results/private'):
        for path in sorted(directory.glob('*.raw')):
            kind='tables'if path.name.startswith('table-')else'numeric'if path.name.startswith('candidate-')else'default'
            if kind!=('tables'if tables else'numeric'if numeric else'default'):continue
            base=path.with_suffix('');dictpath=base.with_suffix('.dict');jp=base.with_suffix('.json')
            if not dictpath.exists() or not jp.exists():continue
            d=z.ZstdCompressionDict(dictpath.read_bytes());comp=base.with_suffix('.zstd');comp.write_bytes(z.ZstdCompressor(level=1,dict_data=d).compress(path.read_bytes()))
            result=subprocess.run([str(exe),str(jp),str(dictpath),str(comp),str(path)],capture_output=True,text=True,check=True)
            row=json.loads(result.stdout);row['fixture']=base.name;rows.append(row)
    assert len(rows)>=2
    (ROOT/'results'/('go-check-tables.json'if tables else'go-check-numeric.json' if numeric else 'go-check.json')).write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
if __name__=='__main__':
    import sys
    run('--numeric' in sys.argv,'--tables' in sys.argv)
