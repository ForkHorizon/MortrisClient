"""Compare completed V2 re-run with original raw artifacts, excluding CPU/TLS."""
import json,hashlib,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
original=ROOT.parents[1]/'transport-v2/04-experiments/results';new=ROOT/'v2-reproduction/results'
files=['sizes_base.md','sizes_rich.md','conservative.md','stateful_base.md','stateful_rich.md','roundtrip.txt','dataset_base.txt','dataset_rich.txt','entropy_floor.txt','example_frame.bin','example_payload.bin','http.md']
out={}
for f in files:
 a=(original/f).read_bytes();b=(new/f).read_bytes()
 out[f]={'identical':a==b,'original_bytes':len(a),'new_bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
print(json.dumps(out,indent=2))
