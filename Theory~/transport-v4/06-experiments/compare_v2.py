import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
old=ROOT.parents[1]/'transport-v2/04-experiments/results'
expected=json.loads((ROOT.parents[1]/'transport-v3/06-experiments/results/reproduction-check.json').read_text());out={}
for name in expected:
 a=(old/name).read_bytes();b=(ROOT/'v2-rerun/results'/name).read_bytes();out[name]={'identical':a==b,'sha256':hashlib.sha256(b).hexdigest()}
assert len(out)==12 and all(x['identical'] for x in out.values())
print(json.dumps(out,indent=2))
