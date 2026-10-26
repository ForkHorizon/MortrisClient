"""Independent C packing, native compressor timing; not a complete native codec.
FFI, Python preprocessing/render and hash verification excluded from stage timings.
"""
import ctypes as c, ctypes.util, json, os, platform, random, statistics, subprocess, time, tracemalloc
from codec import *
from support import ROOT, make, rebatch, drift

R=ROOT/'results'

def measure(fn, repetitions=200):
    samples=[]
    for _ in range(7):
        start=time.perf_counter_ns()
        for __ in range(repetitions):fn()
        samples.append((time.perf_counter_ns()-start)/repetitions/1000)
    return statistics.median(samples)

# This script uses the platform linker rather than hardcoding the Homebrew prefix.
subprocess.run(['clang','-O3','-Wall','-Wextra','-Werror','-shared','-fPIC',str(ROOT/'native.c'),'-o',str(R/'libmtb6.dylib' if platform.system()=='Darwin' else R/'libmtb6.so')],check=True)
lib=c.CDLL(str(R/('libmtb6.dylib' if platform.system()=='Darwin' else 'libmtb6.so')))
lib.mtb6_ints.argtypes=[c.POINTER(c.c_int64),c.c_size_t,c.c_void_p,c.c_size_t];lib.mtb6_ints.restype=c.c_size_t
out=c.create_string_buffer(6000)
rng=random.Random(6006)
cases=[[],[-(1<<63),(1<<63)-1],[0]*500,list(range(500)),[15,0,15,0],[-(1<<63)]*30]
cases += [[rng.randrange(-(1<<63),(1<<63)) for _ in range(rng.randrange(1,501))] for _ in range(1000)]
for xs in cases:
    src=(c.c_int64*len(xs))(*xs)
    size=lib.mtb6_ints(src,len(xs),out,len(out))
    assert out.raw[:size]==integers(xs)
    if size:
        assert lib.mtb6_ints(src,len(xs),out,size-1)==c.c_size_t(-1).value
# The kernel has no allocator symbols; source also contains no allocator calls.
nm=subprocess.run(['nm','-u',str(R/('libmtb6.dylib' if platform.system()=='Darwin' else 'libmtb6.so'))],check=True,capture_output=True,text=True).stdout
assert not any(s in nm for s in ('malloc','calloc','realloc','free'))
zd=c.CDLL(ctypes.util.find_library('zstd'))
zd.ZSTD_versionString.restype=c.c_char_p
zd.ZSTD_createCCtx.restype=c.c_void_p
zd.ZSTD_freeCCtx.argtypes=[c.c_void_p]
zd.ZSTD_compressCCtx.argtypes=[c.c_void_p,c.c_void_p,c.c_size_t,c.c_void_p,c.c_size_t,c.c_int];zd.ZSTD_compressCCtx.restype=c.c_size_t
zd.ZSTD_sizeof_CCtx.argtypes=[c.c_void_p];zd.ZSTD_sizeof_CCtx.restype=c.c_size_t
zd.ZSTD_isError.argtypes=[c.c_size_t];zd.ZSTD_isError.restype=c.c_uint
lz=c.CDLL(ctypes.util.find_library('lz4'))
lz.LZ4_versionString.restype=c.c_char_p
lz.LZ4_compress_default.argtypes=[c.c_void_p,c.c_void_p,c.c_int,c.c_int];lz.LZ4_compress_default.restype=c.c_int
lz.LZ4_decompress_safe.argtypes=[c.c_void_p,c.c_void_p,c.c_int,c.c_int];lz.LZ4_decompress_safe.restype=c.c_int
rows={}
for profile in ('base','rich','alt','drift'):
    ds=drift(1733,1,600) if profile=='drift' else rebatch(make(profile,1729,1),100)
    inst,bs=ds[0];batch=max(bs,key=len)
    schema=Schema.train(drift(202,1,600) if profile=='drift' else rebatch(make(profile,202,1),100))
    aliases=Aliases();aliases.register(inst.install_id,batch)
    raw=encode_raw(schema,aliases,inst.install_id,batch)
    src=c.create_string_buffer(raw);dst=c.create_string_buffer(len(raw)*2+1024)
    ctx=zd.ZSTD_createCCtx()
    def compress(level):
        size=zd.ZSTD_compressCCtx(ctx,dst,len(dst),src,len(raw),level)
        assert not zd.ZSTD_isError(size)
        return size
    compress(1)
    z1=compress(1);z1time=measure(lambda:compress(1));ctx1=zd.ZSTD_sizeof_CCtx(ctx)
    assert z.ZstdDecompressor().decompress(dst.raw[:z1])==raw
    z19=compress(19);z19time=measure(lambda:compress(19),30);ctx19=zd.ZSTD_sizeof_CCtx(ctx)
    assert z.ZstdDecompressor().decompress(dst.raw[:z19])==raw
    def lz4():
        size=lz.LZ4_compress_default(src,dst,len(raw),len(dst));assert size>0;return size
    lzsize=lz4();lztime=measure(lz4)
    restored=c.create_string_buffer(len(raw));assert lz.LZ4_decompress_safe(dst,restored,lzsize,len(raw))==len(raw) and restored.raw==raw
    xs=[e['ts'] for e in batch];iv=(c.c_int64*len(xs))(*xs)
    integer_us=measure(lambda:lib.mtb6_ints(iv,len(xs),out,len(out)))
    # Python full encoding includes schema traversal, packing, compression and canonical rendering.
    tracemalloc.start();frame=encode(schema,aliases,inst.install_id,batch);_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    rows[profile]={'events':len(batch),'raw_bytes':len(raw),'native_zstd1_bytes':z1,'native_zstd1_us':z1time,'zstd1_CCtx_bytes':ctx1,'native_zstd19_bytes':z19,'native_zstd19_us':z19time,'zstd19_CCtx_bytes':ctx19,'native_lz4_block_bytes':lzsize,'native_lz4_us':lztime,'timestamp_integer_column_us_including_FFI':integer_us,'python_full_encode_peak_bytes':peak,'comparison':'same prepared V6 buffer; zstd19 has NO V4 dictionary; not V4/V5 end-to-end'}
    zd.ZSTD_freeCCtx(ctx)
output={'integer_conformance_cases':len(cases),'undersized_buffers_checked':True,'native_kernel_allocator_symbols':False,'undefined_symbols':nm,'zstd':zd.ZSTD_versionString().decode(),'lz4':lz.LZ4_versionString().decode(),'host':platform.platform(),'scope':'native stages only; Python/Unity/ARM/battery/managed-GC excluded','rows':rows}
(R/'native.json').write_text(json.dumps(output,indent=2));print(json.dumps(output,indent=2))
