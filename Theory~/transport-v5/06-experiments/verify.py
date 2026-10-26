"""Research completion evidence; does not certify production C#/Go/Android integration."""
import ast,hashlib,json,re,subprocess
from pathlib import Path
from types import SimpleNamespace
from model import Model,load_artifact
from frame_v5 import decode
R=Path(__file__).resolve().parent;D=R.parent;PROJECT=R.parents[2]
load=lambda n:json.loads((R/'results'/n).read_text())
protected=load('input-sha256.json');changed=[]
for rel,sha in protected.items():
 p=PROJECT/rel
 if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:changed.append(rel)
assert not changed,changed
submission=load('submission-reproduction.json');assert sum(len(v) for v in submission.values())==49
for name,rows in submission.items():
 original=json.loads((D/'review-input/transport-v4-analysis/results'/name).read_text());rerun=json.loads((R/'submission-rerun/results'/name).read_text())
 assert len(original)==len(rerun)
 for a,b in zip(original,rerun):
  if 'B_per_event' in a:assert a['B_per_event']==b['B_per_event']
for name in ['mtb5_session_reset.json','wire.json']:
 assert json.loads((D/'review-input/transport-v4-analysis/results'/name).read_text())==json.loads((R/'submission-rerun/results'/name).read_text())
assert all(x['identical'] for x in load('submission-extra-reproduction.json').values())
assert len({v['frame_sha256'] for v in load('submission-hashseed.json')})>1
counter=load('submission-counterexamples.json');assert counter['extra_zero_accepted'] and counter['failed_decode_mutates_state'] and counter['sent_delta_9999_lost'] and counter['state_token_255_accepted']
for n,count in [('tests.log',8),('recovery-tests.log',3),('extra-tests.log',4),('v4-tests-rerun.log',9)]:
 s=(R/'results'/n).read_text();assert f'Ran {count} tests' in s and s.rstrip().endswith('OK'),(n,s)
mut=load('mutations.json');assert mut['attempts']==2000 and mut['decoded']+mut['rejected']==2000 and mut['prior_unchanged']
native=load('native-conformance.json');assert sum(v['batches_checked'] for v in native.values())==36
manifest=load('model-manifest.json')
for p,entry in manifest.items():
 raw=(R/'results'/f'prior14-{p}.bin').read_bytes();blob=(R/'results'/f'prior14-{p}.zlib').read_bytes()
 assert hashlib.sha256(raw).hexdigest()==entry['raw_sha256'] and hashlib.sha256(blob).hexdigest()==entry['artifact_sha256']
 m=load_artifact(blob,entry['artifact_sha256']);assert m.snapshot()==raw and len(m.probs)*2==65536
 b=load(f'bench-{p}.json');rows=b['rows'];fresh=rows['fresh_holdout'];assert fresh['seed']==(1733 if p=='drift' else 1729)
 assert fresh['stateless']['B_per_event']<fresh['V4_B_per_event']
 for label,row in rows.items():
  a=row['stateless'];assert abs(a['bytes']/a['events']-a['B_per_event'])<1e-12
 assert 'python_pipeline' in b
prior=Model.restore((R/'results/prior14-base.bin').read_bytes());f=(R/'results/example-frame.bin').read_bytes();source,m=decode(prior,f)
assert source==(R/'results/example-source.json').read_bytes()
fixtures=load('fixtures.json');assert fixtures['frame_hex']==f.hex(' ') and len(set(fixtures['cross_process_hashseed_results']))==1
assert fixtures['post_state_id']==m.state_id().hex()
base=Model.restore((R/'results/example-base-state.bin').read_bytes(),state=True);decode(prior,(R/'results/example-stateful-frame.bin').read_bytes(),base=base)
net=load('network.json')['patterns']['offline_900']['models'];assert net['V5_stateless']['wire_B_per_event']['h2_setup0']>net['V4']['wire_B_per_event']['h2_setup0']
assert load('mismatch.json')['V5']['B_per_event']>load('mismatch.json')['V4_wrong_dictionary_B_per_event']
miss=load('miss-cost.json');assert miss[-1]['body_B_per_event_including_failed_requests']>miss[0]['body_B_per_event_including_failed_requests']
required=['00-summary.md','00-iteration-log.md','01-audit.md','03-protocol-spec-v5.md','04-options-comparison.md','05-network-and-recovery.md','07-review-guide.md','08-resource-budget.md','08-rollout-plan.md','09-open-questions.md','10-sources.md']
assert all((D/n).is_file() for n in required)
scripts=list(R.glob('*.py'))
for p in scripts:ast.parse(p.read_text(),filename=str(p))
subprocess.run(['sh','-n',str(R/'run_all.sh')],check=True)
git_available=subprocess.run(['git','rev-parse','--is-inside-work-tree'],cwd=PROJECT,capture_output=True).returncode==0
if git_available:assert not subprocess.check_output(['git','diff','--name-only'],cwd=PROJECT,text=True).strip()
out={'status':'OK','protected_V2_V3_V4_SDK_files_unchanged':len(protected),'submission_body_rows_reproduced':49,'additional_submission_JSONs_identical':2,'V5_test_methods':15,'V4_test_methods_rerun':9,'new_mutations':2000,'native_C_Python_conformance_batches':36,'new_holdout_seeds':[1729,1733],'primary_probabilities_bytes':65536,'fixed_hash_cross_process':True,'offline_wire_and_wrong_prior_regressions_disclosed':True,'scripts_parsed':len(scripts),'documents':len(required),'tracked_product_diff':False if git_available else None,'limitations':'Research candidate. No complete C#/Go/Android/real traffic proof. Stateful recovery is model-only.','script_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in scripts}}
print(json.dumps(out,indent=2))
