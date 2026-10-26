"""Complete Python model accounting, not just probability slots. No C#/ARM claims."""
import sys,gc,json,tracemalloc,zlib
from pathlib import Path
from array import array
from model import Model,context_hash
from support import make,rebatch,drift
from frame_v5 import encode,decode
ROOT=Path(__file__).resolve().parent

def deep(v,seen=None):
    seen=set() if seen is None else seen
    if id(v) in seen:return 0
    seen.add(id(v));size=sys.getsizeof(v)
    if isinstance(v,dict):size+=sum(deep(k,seen)+deep(x,seen) for k,x in v.items())
    elif isinstance(v,(list,tuple)):size+=sum(deep(x,seen) for x in v)
    elif hasattr(v,'__dict__'):size+=deep(v.__dict__,seen)
    return size
out={}
for p in ['base','rich','alt','drift']:
 prior=Model.restore((ROOT/'results'/f'prior14-{p}.bin').read_bytes());ds=drift(1733,4,600) if p=='drift' else rebatch(make(p,1729,6),100);i,bs=ds[0];b=bs[0]
 context_hash.cache_clear();gc.collect();tracemalloc.start();f,m=encode(prior,i.install_id,b);encode_current,encode_peak=tracemalloc.get_traced_memory();tracemalloc.stop()
 context_hash.cache_clear();gc.collect();tracemalloc.start();f,m=encode(prior,i.install_id,b);source,d=decode(prior,f);_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
 out[p]={'probability_bytes_per_model':len(prior.probs)*2,'prior_snapshot_raw_bytes':len(prior.snapshot()),'compressed_prior_asset_bytes':len(prior.artifact()),'prior_Python_object_graph_bytes':deep(prior),'one_post_state_Python_object_graph_bytes':deep(m),'cold_cache_encode_decode_extra_tracemalloc_peak_bytes':peak,'encode_only_extra_tracemalloc_peak_bytes':encode_peak,'encode_only_extra_retained_bytes':encode_current,'first_batch_events':len(b),'context_hash_cache':str(context_hash.cache_info()),'includes_two_candidate_models_and_cache_in_pipeline_peak':True,'prior_model_not_in_tracemalloc_peak':True}
(ROOT/'results/memory.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
