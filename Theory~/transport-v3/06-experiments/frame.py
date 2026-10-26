"""V3 bounded outer framing. Research reference, not production deployment.
Payload kind 0 exact V1-minus-id JSON; 1 canonical MTB2 subset.
"""
import io,zlib,gzip
import zstandard as z
from bench import comp
from wire import uvarint
MAX_FRAME=262144;MAX_RAW=2097152

def read_u(buf,p):
    value=0;start=p
    for shift in range(0,70,7):
        if p>=len(buf):raise ValueError('truncated varint')
        b=buf[p];p+=1
        if shift==63 and b>1:raise ValueError('u64 overflow')
        value|=(b&127)<<shift
        if b<128:
            if buf[start:p]!=uvarint(value):raise ValueError('noncanonical varint')
            return value,p
    raise ValueError('long varint')

def pack(kind,raw,dictionary=None,dict_id=0):
    if kind not in (0,1,2) or not raw or len(raw)>MAX_RAW:raise ValueError('payload')
    options=[(0,0,raw),(1,0,gzip.compress(raw,6,mtime=0)),(2,0,comp(19).compress(raw))]
    if dictionary is not None:
        if not 1<=dict_id<=127:raise ValueError('dict id')
        options.append((2,dict_id,comp(19,dictionary).compress(raw)))
    frames=[bytes([0x30|c,kind])+uvarint(di)+uvarint(len(raw))+b for c,di,b in options]
    frame=min(frames,key=len)
    if len(frame)>MAX_FRAME:raise ValueError('split batch')
    return frame

def unpack(frame,dictionaries):
    if not 5<=len(frame)<=MAX_FRAME or frame[0] not in (0x30,0x31,0x32) or frame[1] not in (0,1,2):raise ValueError('header')
    codec=frame[0]&15;kind=frame[1];di,p=read_u(frame,2);size,p=read_u(frame,p)
    if not 1<=size<=MAX_RAW or (codec!=2 and di):raise ValueError('limits')
    data=frame[p:]
    if codec==0:raw=data
    elif codec==1:
        dec=zlib.decompressobj(31);raw=dec.decompress(data,size+1)
        if not dec.eof or dec.unused_data or dec.unconsumed_tail:raise ValueError('gzip frame')
    else:
        if di and di not in dictionaries:raise ValueError('unknown dictionary')
        try:params=z.get_frame_parameters(b'\x28\xb5\x2f\xfd'+data)
        except z.ZstdError as ex:raise ValueError('zstd header') from ex
        if params.window_size>MAX_RAW or (params.content_size!=z.CONTENTSIZE_UNKNOWN and params.content_size!=size):raise ValueError('zstd limits')
        dec=z.ZstdDecompressor(dict_data=dictionaries.get(di),format=z.FORMAT_ZSTD1_MAGICLESS,max_window_size=2<<20)
        try:raw=dec.decompress(data,max_output_size=size,allow_extra_data=False)
        except z.ZstdError as ex:raise ValueError('zstd frame') from ex
    if len(raw)!=size:raise ValueError('raw length')
    return kind,raw
