"""Reproducible compressor-only Android arm64 probe; no JNI/SDK integration."""
import hashlib,io,json,os,subprocess,tarfile,tempfile,urllib.request,zipfile,ctypes as c
import zstandard as z
from pathlib import Path
ROOT=Path(__file__).resolve().parent
NDK=Path('/Applications/Unity/Hub/Editor/6000.3.16f1/PlaybackEngines/AndroidPlayer/NDK')
URL='https://codeload.github.com/facebook/zstd/tar.gz/refs/tags/v1.5.7'
EXPECTED='37d7284556b20954e56e1ca85b80226768902e2edabd3b649e9e72c0c9012ee3'
def main():
 data=urllib.request.urlopen(URL,timeout=60).read();sha=hashlib.sha256(data).hexdigest()
 if EXPECTED and sha!=EXPECTED:raise ValueError('source hash changed')
 out={'url':URL,'source_sha256':sha,'ndk':(NDK/'source.properties').read_text(),'abi':'arm64-v8a','api':23,'variants':{}}
 with tempfile.TemporaryDirectory() as td:
  td=Path(td)
  with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tar:tar.extractall(td,filter='data')
  src=td/'zstd-1.5.7/lib';wrapper=td/'probe.c'
  wrapper.write_text('''#include "zstd.h"
#include <stdlib.h>
typedef struct {ZSTD_CCtx *ctx; ZSTD_CDict *dict;} State;
__attribute__((visibility("default"))) void *mtb_create(const void *dict,size_t size,int level){State *s=calloc(1,sizeof(State));if(!s)return NULL;s->ctx=ZSTD_createCCtx();s->dict=ZSTD_createCDict(dict,size,level);if(!s->ctx||!s->dict){ZSTD_freeCCtx(s->ctx);ZSTD_freeCDict(s->dict);free(s);return NULL;}return s;}
__attribute__((visibility("default"))) size_t mtb_compress(void *state,void *dst,size_t cap,const void *src,size_t size){State*s=state;return ZSTD_compress_usingCDict(s->ctx,dst,cap,src,size,s->dict);}
__attribute__((visibility("default"))) void mtb_free(void *state){State*s=state;if(s){ZSTD_freeCCtx(s->ctx);ZSTD_freeCDict(s->dict);free(s);}}
''')
  tool=NDK/'toolchains/llvm/prebuilt/darwin-x86_64/bin';cc=tool/'aarch64-linux-android23-clang';strip=tool/'llvm-strip';readelf=tool/'llvm-readelf'
  files=list((src/'common').glob('*.c'))+list((src/'compress').glob('*.c'))
  for label,flags in [('compress_all',[]),('compress_fast',['-DZSTD_EXCLUDE_DFAST_BLOCK_COMPRESSOR','-DZSTD_EXCLUDE_GREEDY_BLOCK_COMPRESSOR','-DZSTD_EXCLUDE_LAZY_BLOCK_COMPRESSOR','-DZSTD_EXCLUDE_LAZY2_BLOCK_COMPRESSOR','-DZSTD_EXCLUDE_BTLAZY2_BLOCK_COMPRESSOR','-DZSTD_EXCLUDE_BTOPT_BLOCK_COMPRESSOR','-DZSTD_EXCLUDE_BTULTRA_BLOCK_COMPRESSOR'])]:
   so=td/(label+'.so');cmd=[str(cc),'-shared','-Oz','-flto','-fPIC','-fvisibility=hidden','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-Wl,--no-undefined','-DZSTD_DISABLE_ASM','-DZSTD_LEGACY_SUPPORT=0','-DZSTD_STRIP_ERROR_STRINGS','-I'+str(src),*flags,str(wrapper),*map(str,files),'-o',str(so)]
   result=subprocess.run(cmd,capture_output=True,text=True)
   if result.returncode:out['variants'][label]={'exit':result.returncode,'stderr':result.stderr};continue
   subprocess.run([str(strip),'--strip-unneeded',str(so)],check=True)
   buf=io.BytesIO()
   with zipfile.ZipFile(buf,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:archive.write(so,'lib/arm64-v8a/libmtb.so')
   symbols=subprocess.run([str(readelf),'--dyn-syms','--wide',str(so)],capture_output=True,text=True,check=True).stdout
   # Same source and exclusions on host verify compressor behavior; Android runtime remains untested.
   host=td/(label+'.dylib')
   hcmd=['cc','-dynamiclib','-Oz','-flto','-fPIC','-fvisibility=hidden','-Wl,-dead_strip','-DZSTD_DISABLE_ASM','-DZSTD_LEGACY_SUPPORT=0','-DZSTD_STRIP_ERROR_STRINGS','-I'+str(src),*flags,str(wrapper),*map(str,files),'-o',str(host)]
   subprocess.run(hcmd,check=True,capture_output=True)
   lib=c.CDLL(str(host));lib.mtb_create.restype=c.c_void_p;lib.mtb_create.argtypes=[c.c_void_p,c.c_size_t,c.c_int];lib.mtb_compress.restype=c.c_size_t;lib.mtb_compress.argtypes=[c.c_void_p,c.c_void_p,c.c_size_t,c.c_void_p,c.c_size_t];lib.mtb_free.argtypes=[c.c_void_p]
   dictionary=(ROOT.parents[1]/'transport-v3/06-experiments/results/dict64_base.bin').read_bytes();db=c.create_string_buffer(dictionary);checks=[]
   for level in ([1] if label=='compress_fast' else [1,3,9,15,19]):
    state=lib.mtb_create(db,len(dictionary),level)
    if not state:raise ValueError('host state')
    for raw in [b'x',b'example_data '*10000,bytes(range(256))*100]:
     rb=c.create_string_buffer(raw);dest=c.create_string_buffer(len(raw)*2+4096);written=lib.mtb_compress(state,dest,len(dest),rb,len(raw))
     if written>len(dest):raise ValueError('native compression error')
     assert z.ZstdDecompressor(dict_data=z.ZstdCompressionDict(dictionary)).decompress(dest.raw[:written])==raw
     checks.append({'level':level,'raw_bytes':len(raw),'compressed_bytes':written})
    lib.mtb_free(state)
   out['variants'][label]={'raw_bytes':so.stat().st_size,'zip_bytes_including_zip_headers':len(buf.getvalue()),'dynamic_symbols':symbols,'compiler_flags':cmd[1:cmd.index(str(wrapper))],'runtime_tested':False,'host_roundtrips':checks,'host_command':hcmd}
 (ROOT/'results/native-build.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
