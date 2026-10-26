"""Asset/RAM tradeoff evaluated only on validation303, not retuned on fresh holdout."""
import json
from pathlib import Path
from support import make,rebatch,drift
from model import Model
from probe_v5 import evaluate
ROOT=Path(__file__).resolve().parent;out={}
for p in ['base','rich','alt','drift']:
 original=Model.restore((ROOT/'results'/f'prior14-{p}.bin').read_bytes());small=original.clone();small.ema.clear()
 ds=drift(303,3,600) if p=='drift' else rebatch(make(p,303,3),100)
 a=evaluate(original,ds);b=evaluate(small,ds)
 out[p]={'dataset':'validation303','full_asset_bytes':len(original.artifact()),'no_ema_asset_bytes':len(small.artifact()),'full_B_per_event':a['B_per_event'],'no_ema_B_per_event':b['B_per_event'],'no_ema_raw_prior_bytes':len(small.snapshot()),'not_primary_holdout_selection':True}
 (ROOT/'results'/f'compact14-{p}.zlib').write_bytes(small.artifact())
(ROOT/'results/compact-prior.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
