"""Portable source/frame fixtures with deterministic alias epochs."""
import base64,json
from codec import *
from support import ROOT,make,rebatch,drift
from schema_tools import pack_schema
out=[]
for profile in ('base','rich','alt','drift'):
    schema=Schema(json.loads((ROOT/'results'/f'schema-{profile}.json').read_text()))
    ds=drift(1733,1,20) if profile=='drift' else rebatch(make(profile,1729,1),20)
    inst,batches=ds[0];b=batches[0]
    a=Aliases(epoch=b'fixture6');payload=a.register(inst.install_id,b)
    for replay in (False,True):
        f=encode(schema,a,inst.install_id,b,replay=replay,preserve_ids=True)
        source=render(inst.install_id,b,True)
        out.append({'profile':profile,'origin':inst.install_id,'schema_binary_hex':pack_schema(schema).hex(),'registration_hex':payload.hex(),'frame_hex':f.hex(),'source_b64':base64.b64encode(source).decode(),'source_sha256':hashlib.sha256(source).hexdigest()})
(ROOT/'results/fixtures.json').write_text(json.dumps(out,indent=2))
print('Saved',len(out),'strict source/frame fixtures')
