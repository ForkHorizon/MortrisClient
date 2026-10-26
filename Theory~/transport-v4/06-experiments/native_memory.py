"""Measure actual zstd-1.5.7 context allocations on host, not Android RSS."""
import ctypes as c,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
lib=c.CDLL('/opt/homebrew/opt/zstd/lib/libzstd.1.5.7.dylib')
def fn(name,rest,args):
 f=getattr(lib,name);f.restype=rest;f.argtypes=args;return f
ptr=c.c_void_p;sz=c.c_size_t;integer=c.c_int
version=fn('ZSTD_versionNumber',c.c_uint,[])
create=fn('ZSTD_createCDict',ptr,[ptr,sz,integer]);byref=fn('ZSTD_createCDict_byReference',ptr,[ptr,sz,integer]);sizeof=fn('ZSTD_sizeof_CDict',sz,[ptr]);free=fn('ZSTD_freeCDict',sz,[ptr])
cc=fn('ZSTD_createCCtx',ptr,[]);cf=fn('ZSTD_freeCCtx',sz,[ptr]);cs=fn('ZSTD_sizeof_CCtx',sz,[ptr]);bound=fn('ZSTD_compressBound',sz,[sz]);compress=fn('ZSTD_compress_usingCDict',sz,[ptr,ptr,sz,ptr,sz,ptr]);err=fn('ZSTD_isError',c.c_uint,[sz])
dc=fn('ZSTD_createDDict',ptr,[ptr,sz]);ds=fn('ZSTD_sizeof_DDict',sz,[ptr]);df=fn('ZSTD_freeDDict',sz,[ptr])
# Use actual trained dictionary from V3, not all-zero fake entropy tables.
dictionary=(ROOT.parents[1]/'transport-v3/06-experiments/results/dict64_base.bin').read_bytes();dbuf=c.create_string_buffer(dictionary)
src=c.create_string_buffer(b'fixed input '*1000);dst=c.create_string_buffer(bound(12000));out={'native_version':version(),'platform':'macOS arm64','rows':[]}
for level in [1,3,6,9,15,19]:
 for ref,creator in [(False,create),(True,byref)]:
  d=creator(dbuf,len(dictionary),level);ctx=cc();n=compress(ctx,dst,len(dst),src,12000,d)
  assert not err(n)
  de=dc(dbuf,len(dictionary));out['rows'].append({'level':level,'by_reference':ref,'CDict_bytes':sizeof(d),'CCtx_after_bytes':cs(ctx),'DDict_bytes':ds(de),'compressed_bytes':n,'dict_source_bytes':len(dictionary)})
  df(de);cf(ctx);free(d)
(ROOT/'results/native-memory.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
