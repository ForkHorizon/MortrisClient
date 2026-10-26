"""Build/store compiler: frozen descriptor -> binary table with presence masks.
No test corpus discovery occurs at runtime. JSON descriptors are audit artifacts.
"""
import json
from codec import Schema, blob, takeblob, u, Reader
from support import ROOT

def pack_schema(schema):
    keys=sorted({k for _,fields in schema.shapes for k,_ in fields})
    names=sorted({name for name,_ in schema.shapes})
    out=bytearray(b'MS6'+schema.id+u(len(names))+u(len(keys)))
    for s in names+keys:out+=blob(s.encode())
    out+=u(len(schema.shapes))
    for name,fields in schema.shapes:
        mask=sum(1<<keys.index(k) for k,_ in fields)
        out+=u(names.index(name))+mask.to_bytes((len(keys)+7)//8,'little')+u(len(fields))
        # Ordered fields retain canonical JSON order and mixed numeric types.
        for k,t in fields:out+=u(keys.index(k))+bytes([t])
    return bytes(out)

def unpack_schema(raw):
    r=Reader(raw)
    if r.take(3)!=b'MS6':raise ValueError('schema magic')
    expected=r.take(8)
    nn,nk=r.count(16000),r.count(16000)
    names=[takeblob(r).decode() for _ in range(nn)]
    keys=[takeblob(r).decode() for _ in range(nk)]
    shapes=[]
    for _ in range(r.count(16000)):
        ni=r.count(nn-1)
        mask=int.from_bytes(r.take((nk+7)//8),'little')
        fields=[]
        for _ in range(r.count(32)):
            ki=r.count(nk-1);fields.append((keys[ki],r.byte()))
        if mask!=sum(1<<keys.index(k) for k,_ in fields):raise ValueError('schema mask')
        shapes.append((names[ni],fields))
    r.end();schema=Schema(shapes)
    if schema.id!=expected:raise ValueError('schema digest')
    return schema

def main():
    rows={}
    for profile in ('base','rich','alt','drift'):
        schema=Schema(json.loads((ROOT/'results'/f'schema-{profile}.json').read_text()))
        raw=pack_schema(schema)
        assert unpack_schema(raw).data==schema.data
        (ROOT/'results'/f'schema-{profile}.bin').write_bytes(raw)
        rows[profile]={'binary_bytes':len(raw),'json_bytes':len(schema.data),'schema_id':schema.id.hex()}
    (ROOT/'results/schema-compilation.json').write_text(json.dumps(rows,indent=2))

if __name__=='__main__':main()
