"""Package consistency checks, separate from codec tests."""
import json,hashlib,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent;DOC=ROOT.parent
required=['00-summary.md','00-iteration-log.md','01-audit.md','02-hypotheses.md','03-protocol-spec-v3.md','04-options-comparison.md','05-ablation.md','07-review-guide.md','08-rollout-plan.md','09-open-questions.md','10-sources.md','06-experiments/README.md']
for name in required:assert (DOC/name).is_file() and (DOC/name).stat().st_size>100,name
assert len((DOC/'00-summary.md').read_text().splitlines())<=15
for claim in range(1,16):assert re.search(r'\| C'+str(claim)+r' \|',(DOC/'01-audit.md').read_text())
for p in ROOT.glob('*.py'):compile(p.read_text(),str(p),'exec')
for f in (ROOT/'results').glob('*.json'):
 if f.name!='verification.json':json.loads(f.read_text())
repro=json.loads((ROOT/'results/reproduction-check.json').read_text());assert len(repro)==12 and all(v['identical'] for v in repro.values())
original=DOC.parent/'transport-v2';manifest=json.loads((ROOT/'results/audit.json').read_text())['v2_sha256']
for name,h in manifest.items():assert hashlib.sha256((original/name).read_bytes()).hexdigest()==h,name
best=json.loads((ROOT/'results/refine.json').read_text());b=json.loads((ROOT/'results/bench.json').read_text())['profiles'];final=json.loads((ROOT/'results/final-passes.json').read_text())
for p in ['base','rich','alt']:
 assert best[p]['best']<b[p]['body_B_per_event']['V2_dict16_l19']
 for method in ['linear','per_type','ultra22','ldm19']:assert (1-final[p][method]/final[p]['best'])<.02
 t=json.loads((ROOT/'results/v3-tests.json').read_text());assert t['mutations_rejected']+t['mutations_decoded']==2000
ex=json.loads((ROOT/'results/extras.json').read_text())['example'];raw=(ROOT/'results/example-frame.bin').read_bytes();assert raw.hex()==ex['hex'] and len(raw)==ex['frame_bytes']
print(json.dumps({'required_files':len(required),'claims_C1_C15':15,'v2_files_unchanged':len(manifest),'deterministic_reproductions_identical':len(repro),'summary_lines':len((DOC/'00-summary.md').read_text().splitlines()),'python_scripts_compiled':len(list(ROOT.glob('*.py'))),'two_stopping_passes_below_2pct':True,'status':'OK'},indent=2))
