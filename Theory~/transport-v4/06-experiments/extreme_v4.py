"""Matched cap500/train202/64KiB comparison; synthetic rule is explicitly conditional."""
import json
from pathlib import Path
from bench_v4 import CONFIGS,measure
from workloads import make,rebatch
ROOT=Path(__file__).resolve().parent
CONFIGS.update(cleanreplay={**CONFIGS['clean'],'replay':True},cleanreplaytail={**CONFIGS['clean'],'replay':True,'trailer':True},replaytail={**CONFIGS['trailer'],'replay':True})
out={}
for p in ['base','rich','alt']:
 tr=rebatch(make(p,202,18),500);te=rebatch(make(p,101,6),500);row={}
 for model in ['V3replay','trailer','cleanreplay','cleanreplaytail','replaytail']:
  row[model]=measure(te,tr,model,65536);print(p,model,row[model]['B_per_event'],flush=True)
 out[p]=row;(ROOT/'results/extreme-v4.json').write_text(json.dumps(out,indent=2))
