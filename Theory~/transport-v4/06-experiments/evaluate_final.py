"""One selection from validation303, then untouched seed909 and independent drift808."""
import json,math,time,gzip,statistics,tracemalloc,sys
from pathlib import Path
import zstandard as z
import core,wire,framing,exact
from workloads import make,rebatch,drift
from bench_v4 import CONFIGS,blobs
from bench import comp
from frame import pack as pack3
ROOT=Path(__file__).resolve().parent

def main():
 matrix=json.loads((ROOT/'results/paired-matrix.json').read_text())
 names=['base','rich','alt'];candidates=['clean','packed','noef','trailer']
 scores={m:sum(math.log(matrix['profiles'][p]['validation']['rows'][m]['B_per_event']/matrix['profiles'][p]['validation']['rows']['clean']['B_per_event']) for p in names)/3 for m in candidates}
 chosen=min(scores,key=scores.get);out={'selection':{'source':'validation seed303 only, equal-weight log relative bytes across three profiles','scores':scores,'chosen':chosen},'profiles':{}}
 (ROOT/'results/selection.json').write_text(json.dumps(out['selection'],indent=2))
 for name in names+['drift']:
  if name=='drift':train=drift(202,12,600);test=drift(808,4,600)
  else:train=rebatch(make(name,202,18),100);test=rebatch(make(name,909,6),100)
  t4=blobs(train,chosen);d4=z.train_dictionary(65536,[r for _,_,r,_ in t4],level=19)
  t3=blobs(train,'V3');d3=z.train_dictionary(65536,[r for _,_,r,_ in t3],level=19)
  n=sum(len(b) for _,bs in test for b in bs);x4=blobs(test,chosen);x3=blobs(test,'V3');row={'events':n,'batches':len(x4),'model':chosen,'levels':{},'seed':808 if name=='drift' else 909}
  row['V3_levels']={}
  for lev in [1,3,6,9,15,19]:
   ctx=framing.compressor(lev,d3);total=0;maximum=0
   for _,_,r,_ in x3:
    total+=3+len(wire.uvarint(len(r)))+len(ctx.compress(r));maximum=max(maximum,ctx.memory_size())
   row['V3_levels'][str(lev)]={'B_per_event':total/n,'CCtx_size_max':maximum}
  row['V3_l19_B_per_event']=sum(len(pack3(1,r,d3,1)) for _,_,r,_ in x3)/n
  for level in [1,3,6,9,15,19]:
   ctx=framing.compressor(level,d4);total=0;times=[];python_peaks=[];mem=[]
   for inst,b,r,t in x4:
    start=time.perf_counter_ns();compressed=ctx.compress(r);times.append((time.perf_counter_ns()-start)/1000)
    # Full encoder includes raw candidate and exact outer fields.
    f=framing.pack(r,t,len(b),d4,1,level);_,rr,tt,nn=framing.unpack(f,{1:d4});_,ev=core.decode(rr,tt);assert exact.render(inst,ev)==exact.render(inst,b)
    total+=len(f);mem.append(ctx.memory_size())
   row['levels'][str(level)]={'B_per_event':total/n,'compression_p50_us':statistics.median(times),'compression_p95_us':sorted(times)[int(.95*(len(times)-1))],'CCtx_size_max':max(mem)}
  # Constrained match tables: actual codec roundtrip and context memory, identical dictionary bytes.
  row['small_tables']={};row['V3_small_tables']={}
  for log in [12,14,16]:
   p=z.ZstdCompressionParameters.from_level(3,format=z.FORMAT_ZSTD1_MAGICLESS,write_content_size=False,write_checksum=False,write_dict_id=False,window_log=17,hash_log=log,chain_log=log)
   ctx=z.ZstdCompressor(compression_params=p,dict_data=d4);total=0;maximum=0
   for inst,b,r,t in x4:
    compressed=ctx.compress(r);frame=bytes([0x42,1])+wire.uvarint(len(b))+b'\x01'+wire.uvarint(len(r))+wire.uvarint(len(t))+compressed+t
    _,rr,tt,nn=framing.unpack(frame,{1:d4});assert (rr,tt)==(r,t)
    total+=len(frame);maximum=max(maximum,ctx.memory_size())
   row['small_tables'][str(log)]={'B_per_event':total/n,'CCtx_size_max':maximum}
   ctx3=z.ZstdCompressor(compression_params=p,dict_data=d3);total3=0;max3=0
   for _,_,r,_ in x3:total3+=3+len(wire.uvarint(len(r)))+len(ctx3.compress(r));max3=max(max3,ctx3.memory_size())
   row['V3_small_tables'][str(log)]={'B_per_event':total3/n,'CCtx_size_max':max3}
  # End-to-end Python pipeline, including structure, compression, full parse and byte verification.
  times=[];peaks=[]
  for inst,b,_,_ in x4[:30]:
   tracemalloc.start();start=time.perf_counter_ns();r,t=core.encode(inst,b,**CONFIGS[chosen]);f=framing.pack(r,t,len(b),d4,1,9);_,rr,tt,_=framing.unpack(f,{1:d4});_,ev=core.decode(rr,tt);assert exact.render(inst,ev)==exact.render(inst,b)
   times.append((time.perf_counter_ns()-start)/1e6);_,peak=tracemalloc.get_traced_memory();tracemalloc.stop();peaks.append(peak)
  normal=[];reused=framing.compressor(9,d4)
  for inst,b,_,_ in x4[:30]:
   start=time.perf_counter_ns();r,t=core.encode(inst,b,**CONFIGS[chosen]);f=framing.pack(r,t,len(b),d4,1,9,context=reused);_,rr,tt,_=framing.unpack(f,{1:d4});_,ev=core.decode(rr,tt);assert exact.render(inst,ev)==exact.render(inst,b);normal.append((time.perf_counter_ns()-start)/1e6)
  row['python_pipeline']={'uninstrumented_p50_ms':statistics.median(normal),'uninstrumented_p95_ms':sorted(normal)[int(.95*(len(normal)-1))],'batches':len(times),'p50_ms_with_tracemalloc':statistics.median(times),'p95_ms_with_tracemalloc':sorted(times)[int(.95*(len(times)-1))],'peak_tracemalloc_bytes':max(peaks),'native_allocations_included':False}
  # Same negotiated frame vs compressed raw payload using standard-library gzip, no dictionary cost.
  row['gzip6_B_per_event']=sum(len(bytes([0x41,1])+wire.uvarint(len(b))+b'\x00'+wire.uvarint(len(r))+wire.uvarint(len(t))+gzip.compress(r,6,mtime=0)+t) for _,b,r,t in x4)/n
  if name!='drift':
   sessiontest=rebatch(make(name,909,6),100,session=True,deadline=30000);xs=blobs(sessiontest,chosen)
   row['session_deadline30s']={'batches':len(xs),'B_per_event':sum(len(framing.pack(r,t,len(b),d4,1,9)) for _,b,r,t in xs)/n,'dictionary_training':'cap100 backlog dictionary, unchanged to isolate boundaries'}
  out['profiles'][name]=row;(ROOT/'results/holdout-resources.json').write_text(json.dumps(out,indent=2));print(name,chosen,row['levels'],flush=True)
if __name__=='__main__':main()
