import json
from pathlib import Path
import zstandard as z
from support import drift,core
from model import Model
from probe_v5 import evaluate
from framing import pack
ROOT=Path(__file__).resolve().parent
p=Model.restore((ROOT/'results/prior14-base.bin').read_bytes());ds=drift(1733,4,600);r=evaluate(p,ds)
d=z.ZstdCompressionDict((ROOT.parents[1]/'transport-v4/06-experiments/results/dict-base-trailer.bin').read_bytes());total=n=0
for i,bs in ds:
 for b in bs:
  raw,t=core.encode(i,b,trailer=True);total+=len(pack(raw,t,len(b),d,1,19));n+=len(b)
out={'prior':'base train202 used on different drift product','test':'fresh drift1733','V5':r,'V4_wrong_dictionary_B_per_event':total/n,'not_generalization_proof':'Cross-product mismatch, not adjacent real releases'}
(ROOT/'results/mismatch.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
