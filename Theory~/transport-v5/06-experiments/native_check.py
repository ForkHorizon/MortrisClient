"""Cross-language entropy conformance and stage-only timing, not complete encoder CPU."""
import ctypes as c,json,subprocess,sys,time,statistics
from pathlib import Path
from support import make,rebatch
from model import Model,context_slot
from context_codec import Coder,code_batch
ROOT=Path(__file__).resolve().parent;BUILD=ROOT/'build';BUILD.mkdir(exist_ok=True)
libpath=BUILD/'range_native.dylib'
subprocess.run(['cc','-dynamiclib','-O3','-fPIC',str(ROOT/'range_native.c'),'-o',str(libpath)],check=True)
lib=c.CDLL(str(libpath));fn=lib.mtb5_entropy
fn.argtypes=[c.c_void_p,c.c_uint,c.c_void_p,c.c_void_p,c.c_size_t,c.c_void_p,c.c_size_t,c.c_void_p,c.c_void_p];fn.restype=c.c_int
class Trace(Coder):
 def bit(self,ctx,b=None):
  self.indices.append(context_slot(ctx,self.m.bits));self.values.append(int(b));return super().bit(ctx,b)
out={}
for p in ['base','rich','alt']:
 prior=Model.restore((ROOT/'results'/f'prior14-{p}.bin').read_bytes());samples=[(i,b) for i,bs in rebatch(make(p,101,6),100) for b in bs][:12];total=events=0;times=[];checks=0
 for inst,batch in samples:
  m=prior.clone();m.reset_batch_state();m.last[('install',)]=inst.install_id;trace=Trace(m,True);trace.indices=[];trace.values=[];code_batch(trace,inst.install_id,batch,True);want=trace.rc.finish()
  indices=(c.c_uint32*len(trace.indices))(*trace.indices);values=(c.c_uint8*len(trace.values))(*trace.values);pr=c.create_string_buffer(prior.probs.tobytes());final=c.create_string_buffer(len(prior.probs)*2);dest=c.create_string_buffer(max(4096,len(trace.values)+32));written=c.c_size_t()
  for _ in range(7):
   t=time.perf_counter_ns();result=fn(pr,prior.bits,indices,values,len(trace.values),dest,len(dest),c.byref(written),final);times.append((time.perf_counter_ns()-t)/len(batch)/1000)
   assert result==0 and dest.raw[:written.value]==want and final.raw==m.probs.tobytes()
  checks+=1;total+=len(trace.values);events+=len(batch)
 out[p]={'batches_checked':checks,'events':events,'binary_decisions':total,'stage_us_per_event_p50':statistics.median(times),'working_probability_bytes':len(prior.probs)*2,'prior_probability_bytes':len(prior.probs)*2,'excludes':'context hash/serialization/lookup, predictors, string tables, source/JSON/CRC, frame, ACK. Not total encoder/ARM time.'}
(ROOT/'results/native-conformance.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
