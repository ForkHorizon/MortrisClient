"""Hash this evidence snapshot, excluding private payloads and build/tool caches."""
import hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
TARGET=ROOT/'06-experiments/results/artifacts-sha256.json'

def manifest():
    result={}
    ignored={'private','bin','obj','obj-unity','__pycache__','.venv'}
    for directory,subdirs,names in os.walk(ROOT):
        subdirs[:]=sorted(name for name in subdirs if name not in ignored)
        for name in sorted(names):
            p=Path(directory)/name
            if p==TARGET or p.name=='run-all.log':continue
            result[str(p.relative_to(ROOT))]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    return result
if __name__=='__main__':
    import sys
    if '--check' in sys.argv:
        assert json.loads(TARGET.read_text())==manifest(),'V7 snapshot changed'
        print('V7 artifact hashes verified')
    else:
        TARGET.write_text(json.dumps(manifest(),indent=2));print('V7 evidence snapshot hashed')
