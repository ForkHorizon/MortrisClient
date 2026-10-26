"""MTB4 bounded framing. Retains standard magicless zstd headers."""
import gzip,zlib
import zstandard as z
from primitives import Reader,u
MAX_FRAME=262144;MAX_RAW=2097152

def compressor(level,d=None):
    p=z.ZstdCompressionParameters.from_level(level,format=z.FORMAT_ZSTD1_MAGICLESS,write_content_size=False,write_checksum=False,write_dict_id=False,window_log=20)
    return z.ZstdCompressor(compression_params=p,dict_data=d)
def limit(n):return min(MAX_RAW,4096+n*8704)
def pack(raw,tail,n,d=None,di=0,level=9,kind=1,adaptive=False,context=None):
    if not 1<=n<=500 or kind not in (0,1,2) or not raw or len(raw)+len(tail)>limit(n):raise ValueError('limits')
    opts=[(0,0,raw)]
    if d is not None and not 1<=di<=127:raise ValueError('dict id')
    opts.append((2,di if d is not None else 0,(context if context is not None else compressor(level,d)).compress(raw)))
    if adaptive:
        opts.extend([(1,0,gzip.compress(raw,6,mtime=0)),(2,0,compressor(level).compress(raw))])
    frames=[bytes([0x40|c,kind])+u(n)+u(idx)+u(len(raw))+u(len(tail))+b+tail for c,idx,b in opts]
    out=min(frames,key=len)
    if len(out)>MAX_FRAME:raise ValueError('split batch')
    return out

def unpack(frame,dicts):
    if not 6<=len(frame)<=MAX_FRAME:raise ValueError('frame length')
    r=Reader(frame);h=r.byte();kind=r.byte()
    if h not in (0x40,0x41,0x42) or kind not in (0,1,2):raise ValueError('header')
    n=r.count(500);di=r.count(127);size=r.u();nt=r.u()
    if not n or not size or size+nt>limit(n) or nt>len(frame)-r.p or (h!=0x42 and di):raise ValueError('limits')
    data=r.take(len(frame)-r.p-nt);tail=r.take(nt)
    if h==0x40:raw=data
    elif h==0x41:
        dec=zlib.decompressobj(31);raw=dec.decompress(data,size+1)
        if not dec.eof or dec.unused_data or dec.unconsumed_tail:raise ValueError('gzip boundary')
    else:
        if di and di not in dicts:raise ValueError('dictionary')
        try:
            params=z.get_frame_parameters(b'\x28\xb5\x2f\xfd'+data)
            if params.window_size>MAX_RAW or (params.content_size!=z.CONTENTSIZE_UNKNOWN and params.content_size!=size):raise ValueError('zstd parameters')
            dec=z.ZstdDecompressor(dict_data=dicts.get(di),format=z.FORMAT_ZSTD1_MAGICLESS,max_window_size=MAX_RAW)
            raw=dec.decompress(data,max_output_size=size,allow_extra_data=False)
        except z.ZstdError as ex:raise ValueError('zstd') from ex
    if len(raw)!=size:raise ValueError('raw length')
    return kind,raw,tail,n
