"""Completion evidence, scoped assertions; not a production correctness certificate."""
import ast,hashlib,json,math,re,subprocess,sys
from pathlib import Path
import core,exact,framing,transport
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[2];D=ROOT.parent
read=lambda n:json.loads((ROOT/'results'/n).read_text())
old=read('input-sha256.json');changed=[]
for path,sha in old.items():
 p=PROJECT/path
 if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:changed.append(path)
assert not changed,changed
fresh=read('v2-fresh-comparison.json');assert len(fresh)==12 and all(v['identical'] for v in fresh.values())
# Compare actual fresh bytes, not just a cached green summary.
for name,v in fresh.items():
 a=(ROOT/'v2-rerun/results'/name).read_bytes();b=(ROOT.parents[1]/'transport-v2/04-experiments/results'/name).read_bytes()
 assert a==b and hashlib.sha256(a).hexdigest()==v['sha256']
assert 'done' in (ROOT/'results/v2-full-rerun.log').read_text()
v3=read('v3-tests-rerun.json');assert v3['equivalent_events']==8233
external=read('external-audit.json');assert external['supplied_selftests']['exit']==0 and not external['lexeme_roundtrips']['-0.00']['exact']
assert external['digest_omitted_fields_collision'] and external['truncated_zlib_accepted'] and external['deflate_bomb_python_peak_bytes']>2000000
# Unmodified original report and code fences retained.
report=(D/'review-input/external-review.md').read_text();blocks=re.findall(r'```python\n(.*?)```',report,re.S)
for n,s in zip(['v4_codec.py','v4_audit_and_bench.py'],blocks):assert (D/'review-input'/n).read_text()==s
m=read('paired-matrix.json')['profiles'];ref=json.loads((ROOT.parents[1]/'transport-v3/06-experiments/results/refine.json').read_text());nrows=0
for p,rs in m.items():
 assert abs(rs['100/65536/V3']['B_per_event']-ref[p]['best'])<1e-10
 for label,row in rs.items():
  if label=='validation':continue
  assert abs(row['bytes']/row['events']-row['B_per_event'])<1e-12;nrows+=1
held=read('holdout-resources.json');assert held['selection']['chosen']=='trailer'
assert held['profiles']['drift']['levels']['19']['B_per_event']>held['profiles']['drift']['V3_l19_B_per_event']
for row in held['profiles'].values():
 assert 'uninstrumented_p50_ms' in row['python_pipeline']
 assert row['small_tables']['12']['CCtx_size_max']<row['levels']['19']['CCtx_size_max']
fixture=(ROOT/'results/example-frame.bin').read_bytes();dictionary=(ROOT/'results/dict-base-trailer.bin').read_bytes()
import zstandard as z
_,r,t,n=framing.unpack(fixture,{1:z.ZstdCompressionDict(dictionary)});meta,ev=core.decode(r,t)
assert n==len(ev)==20 and exact.render(SimpleNamespace(install_id=meta['install_id']),ev)==(ROOT/'results/example-source.json').read_bytes()
assert fixture.hex(' ')==read('example.json')['frame_hex']
logs=(ROOT/'results/tests.log').read_text();assert 'Ran 9 tests' in logs and logs.rstrip().endswith('OK')
fuzz=read('fuzz.json');assert sum(fuzz[k] for k in ['outer_rejected','core_rejected','decoded'])==3000 and fuzz['payload_rejected']+fuzz['payload_decoded']==3000
low=read('memory-floor.json');assert sum(len(v) for v in low.values())==18
native=read('native-build.json');assert sum(len(v['host_roundtrips']) for v in native['variants'].values())==18
assert all(v['raw_bytes']>0 and not v['runtime_tested'] for v in native['variants'].values())
assert native['source_sha256']=='37d7284556b20954e56e1ca85b80226768902e2edabd3b649e9e72c0c9012ee3'
assert all(v['improvement_pct']<2 for row in read('final-passes-v4.json').values() for v in row['passes'].values())
required=['00-summary.md','00-iteration-log.md','01-audit.md','02-hypotheses.md','03-protocol-spec-v4.md','04-options-comparison.md','05-ablation.md','07-review-guide.md','08-resource-budget.md','08-rollout-plan.md','09-open-questions.md','10-sources.md']
assert all((D/p).is_file() for p in required)
assert len((D/'00-summary.md').read_text().splitlines())==15
scripts=list(ROOT.glob('*.py'))
for p in scripts:ast.parse(p.read_text(),filename=str(p))
subprocess.run(['sh','-n',str(ROOT/'run_all.sh')],check=True)
git_available=subprocess.run(['git','rev-parse','--is-inside-work-tree'],cwd=PROJECT,capture_output=True).returncode==0
if git_available:assert not subprocess.check_output(['git','diff','--name-only'],cwd=PROJECT,text=True).strip()
out={'status':'OK','unchanged_input_files':len(old),'fresh_V2_identical_artifacts':12,'V3_roundtrip_events':8233,'paired_matrix_rows':nrows,'V4_roundtrip_event_checks':read('roundtrip-count.json')['events_including_both_modes'],'test_methods':9,'mutations':6000,'native_host_roundtrips':18,'documents':len(required),'scripts_parsed':len(scripts),'full_fixture_events':20,'holdout_regression_disclosed':True,'two_final_passes_below_2pct':True,'tracked_product_diff':False if git_available else None,'scope':'research package; no Android runtime/production traffic certification','script_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in scripts}}
print(json.dumps(out,indent=2))
