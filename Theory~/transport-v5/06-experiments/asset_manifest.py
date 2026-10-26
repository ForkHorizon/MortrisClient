import json,hashlib
from pathlib import Path
from model import load_artifact
ROOT=Path(__file__).resolve().parent;out={}
for p in ['base','rich','alt','drift']:
 raw=(ROOT/'results'/f'prior14-{p}.bin').read_bytes();blob=(ROOT/'results'/f'prior14-{p}.zlib').read_bytes();sha=hashlib.sha256(blob).hexdigest();m=load_artifact(blob,sha);assert m.snapshot()==raw
 out[p]={'model_id':1,'experiment':'separate profile/build; not four dictionaries selected for free at runtime','codec_abi':'mtb5-ctx-v1','bits':14,'artifact_bytes':len(blob),'raw_bytes':len(raw),'artifact_sha256':sha,'raw_sha256':hashlib.sha256(raw).hexdigest(),'max_decompressed_asset':6291456}
(ROOT/'results/model-manifest.json').write_text(json.dumps(out,indent=2))
