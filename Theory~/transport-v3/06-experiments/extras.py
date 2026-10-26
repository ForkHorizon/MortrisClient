"""Dictionary patch sizes, exact sample, artifact checksum checks."""
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'transport-v2/04-experiments'))
from gen import dataset
from codec import safe_payload
from frame import pack,unpack
import wire,zstandard as z
out={};base=(ROOT/'results/dict64_base.bin').read_bytes()
for name in ('base','rich','alt'):
 raw=(ROOT/'results'/('dict64_'+name+'.bin')).read_bytes()
 dd=z.ZstdCompressionDict(base,dict_type=z.DICT_TYPE_RAWCONTENT)
 patch=z.ZstdCompressor(level=19,dict_data=dd).compress(raw)
 assert z.ZstdDecompressor(dict_data=dd).decompress(patch)==raw
 out[name]={'full_bytes':len(raw),'patch_from_base_bytes':len(patch),'sha256':hashlib.sha256(raw).hexdigest()}
inst,bs=dataset(101,installs=1)[0];batch=[e for b in bs for e in b][:20]
d=z.ZstdCompressionDict(base);kind,payload=safe_payload(inst,batch);frame=pack(kind,payload,d,1)
assert unpack(frame,{1:d})==(kind,payload)
(ROOT/'results/example-v1.json').write_bytes(wire.v1_json(inst,batch,True));(ROOT/'results/example-payload.bin').write_bytes(payload);(ROOT/'results/example-frame.bin').write_bytes(frame)
out['example']={'events':20,'kind':kind,'raw_v1_bytes':len(wire.v1_json(inst,batch,True)),'payload_bytes':len(payload),'frame_bytes':len(frame),'B_event':len(frame)/20,'frame_sha256':hashlib.sha256(frame).hexdigest(),'hex':frame.hex()}
# Verify original V2 content remained unmodified (ignore Python-generated caches).
before=json.loads((ROOT/'results/audit.json').read_text())['v2_sha256'];v2=ROOT.parents[1]/'transport-v2'
out['v2_changed']=[p for p,h in before.items() if hashlib.sha256((v2/p).read_bytes()).hexdigest()!=h]
assert not out['v2_changed']
print(json.dumps(out,indent=2))
