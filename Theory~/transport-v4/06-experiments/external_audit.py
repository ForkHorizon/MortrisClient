"""Execute supplied reference, then explicit counterexamples; no inferred benchmarks."""
import sys,json,subprocess,struct,zlib,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'review-input'))
import v4_codec as ext
out={}
p=subprocess.run([sys.executable,str(ROOT.parent/'review-input/v4_audit_and_bench.py')],capture_output=True,text=True)
out['supplied_selftests']={'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
out['lexeme_roundtrips']={}
for lex in ['-0.00','-0.000','0.0','120.00','1.7976931348623157e+308','5e-324']:
 t,b=ext.encode_alp_number(lex);v,pos=ext.decode_alp_number(t,b,0);out['lexeme_roundtrips'][lex]={'decoded':v,'exact':lex==v,'consumed':pos==len(b)}
e={'sequence':1,'timestamp_ms':123,'event_name':'x','session_id':'a','device_class':'phone','properties':{'a':1,'b':2}}
e2={**e,'session_id':'b','device_class':'tablet'}
e3={**e,'properties':{'b':2,'a':1}}
out['digest_omitted_fields_collision']=ext.canonical_event_digest(e,'origin')==ext.canonical_event_digest(e2,'origin')
out['digest_order_sensitive']=ext.canonical_event_digest(e,'origin')!=ext.canonical_event_digest(e3,'origin')
for label,xs in [('empty',[]),('uint64',[2**64-1]),('int64_jump',[-2**63,2**63-1])]:
 try:
  b=ext.encode_int_column(xs);v,pos=ext.decode_int_column(b,0,len(xs));out[label]={'exact':v==xs,'consumed':pos==len(b)}
 except Exception as ex:out[label]={'error':type(ex).__name__+': '+str(ex)}
f=ext.pack_v4_frame(b'hello'*100,b'',1);r=ext.read_uvarint(f,2);_,pos=ext.read_uvarint(f,r[1]);_,pos=ext.read_uvarint(f,pos)
out['zstd_header_still_present']=f[0]==0x42 and f[pos]==0
# Truncated deflate missing checksum is accepted because eof is never checked.
bomb=zlib.compress(b'x'*2000000)
truncated=b'\x41'+ext.put_uvarint(1)+b'\x00'+ext.put_uvarint(10)+b'\x00'+bomb
try:ext.unpack_v4_frame(truncated,{});out['deflate_bomb']='accepted'
except Exception as ex:out['deflate_bomb']=type(ex).__name__
# Instrument allocation from unbounded flush, without relying on exception size.
import tracemalloc
tracemalloc.start()
try:ext.unpack_v4_frame(truncated,{})
except Exception:pass
_,peak=tracemalloc.get_traced_memory();tracemalloc.stop();out['deflate_bomb_python_peak_bytes']=peak
z=zlib.compress(b'hello')[:-4];f=b'\x41\x01\x00\x05\x00'+z
try:out['truncated_zlib_accepted']=ext.unpack_v4_frame(f,{})[0]==b'hello'
except Exception:out['truncated_zlib_accepted']=False
ack_for=lambda seqs:ext.make_request_bound_ack(b'origin',seqs[0],len(seqs),1)
out['ack_same_first_count_ignores_sequence_gaps']=ack_for([1,2,5])==ack_for([1,3,5])
out['missing_full_codec_functions']=[s for s in ['encode_batch','decode_batch','rANS','Chimp128','EliasFano'] if not hasattr(ext,s)]
(ROOT/'results/external-audit.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
