import json
from pathlib import Path
R=Path(__file__).resolve().parent;old=R.parent/'review-input/transport-v4-analysis/results';new=R/'submission-rerun/results';out={}
for name in ['baseline_v4.json','mtb5_base.json','mtb5_rich.json','mtb5_alt.json','mtb5_drift.json']:
 a=json.loads((old/name).read_text());b=json.loads((new/name).read_text());rows=[]
 assert len(a)==len(b)
 for x,y in zip(a,b):
  if 'B_per_event' not in x:continue
  assert x['B_per_event']==y['B_per_event']
  rows.append({k:x.get(k) for k in ['profile','test','cap','stateful','hash_rule','B_per_event']})
 out[name]=rows
assert sum(len(v) for v in out.values())==49
(R/'results/submission-reproduction.json').write_text(json.dumps(out,indent=2))
extra={}
for name in ['mtb5_session_reset.json','wire.json']:
 a=json.loads((old/name).read_text());b=json.loads((new/name).read_text());assert a==b;extra[name]={'identical':True}
(R/'results/submission-extra-reproduction.json').write_text(json.dumps(extra,indent=2))
