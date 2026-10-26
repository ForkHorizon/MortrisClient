"""Deterministic bounded probability table and explicit prior/state serialization.
Python metadata maps are part of measured memory; this is not a zero-allocation C# port.
"""
import hashlib,json,struct,sys,zlib
from array import array
from decimal import Decimal
from functools import lru_cache
from support import Reader,u
MAX_AUX=65536;MAX_TABLE_BYTES=1048576

def context_bytes(v):
    if v is None:return b'\x00'
    if isinstance(v,str):
        b=v.encode('utf-8','surrogatepass');return b'\x01'+u(len(b))+b
    if type(v) is int:return b'\x02'+u((v<<1) if v>=0 else (-v*2-1))
    if type(v) is tuple:return b'\x03'+u(len(v))+b''.join(context_bytes(x) for x in v)
    raise ValueError('context type')
@lru_cache(maxsize=32768)
def context_hash(v):return int.from_bytes(hashlib.blake2s(context_bytes(v),digest_size=8,person=b'MTB5ctx').digest(),'little')
def context_slot(ctx,bits):return context_hash(ctx)&((1<<bits)-1)

def typed(v):
    if v is None:return [0]
    if type(v) is bool:return [1,int(v)]
    if type(v) is int:return [2,str(v)]
    if isinstance(v,str):return [3,v]
    if isinstance(v,tuple):return [4,[typed(x) for x in v]]
    if isinstance(v,list):return [5,[typed(x) for x in v]]
    if isinstance(v,dict):return [6,[[typed(k),typed(x)] for k,x in v.items()]]
    if type(v) is float:return [7,struct.pack('<d',v).hex()]
    if isinstance(v,Decimal):return [8,str(v)]
    raise ValueError('state type')
def untyped(x,depth=0):
    if depth>32 or not isinstance(x,list) or not x:raise ValueError('state schema')
    tag=x[0]
    if tag==0:return None
    if len(x)!=2:raise ValueError('state item')
    v=x[1]
    if tag==1:return bool(v)
    if tag==2:return int(v)
    if tag==3:return str(v)
    if tag in (4,5):
        out=[untyped(z,depth+1) for z in v];return tuple(out) if tag==4 else out
    if tag==6:return {untyped(k,depth+1):untyped(z,depth+1) for k,z in v}
    if tag==7:return struct.unpack('<d',bytes.fromhex(v))[0]
    if tag==8:return Decimal(v)
    raise ValueError('state tag')
class Model:
    def __init__(self,bits=14):
        if not 10<=bits<=18:raise ValueError('table bits')
        self.bits=bits;self.probs=array('H',[32768])*(2<<bits);self.tables={};self.tidx={};self.last={};self.ema={};self.table_bytes=0;self.table_entries=0
    def clone(self):
        m=Model.__new__(Model);m.bits=self.bits;m.probs=self.probs[:];m.tables={k:v[:] for k,v in self.tables.items()};m.tidx={k:dict(v) for k,v in self.tidx.items()};m.last=dict(self.last);m.ema=dict(self.ema);m.table_bytes=self.table_bytes;m.table_entries=self.table_entries;return m
    def reset_batch_state(self):self.last={}
    def check_budget(self):
        if len(self.last)+len(self.ema)+len(self.tables)>MAX_AUX or self.table_bytes>MAX_TABLE_BYTES or self.table_entries>8192:raise ValueError('auxiliary state budget')
    def snapshot(self,state=False):
        probs=self.probs[:]
        if sys.byteorder!='little':probs.byteswap()
        extra=[typed(self.tables),typed(self.ema)]
        if state:extra.append(typed(self.last))
        data=json.dumps(extra,ensure_ascii=True,separators=(',',':')).encode('ascii')
        if len(data)>4*MAX_TABLE_BYTES:raise ValueError('snapshot budget')
        return b'MTB5P1'+bytes([self.bits,int(state)])+u(len(data))+probs.tobytes()+data
    @classmethod
    def restore(cls,raw,*,state=False):
        if len(raw)>6*MAX_TABLE_BYTES:raise ValueError('snapshot size')
        r=Reader(raw)
        if r.take(6)!=b'MTB5P1':raise ValueError('snapshot magic')
        bits=r.byte();flag=r.byte();n=r.count(4*MAX_TABLE_BYTES);m=cls(bits)
        if flag!=int(state):raise ValueError('snapshot kind')
        values=array('H');values.frombytes(r.take((4<<bits)))
        if sys.byteorder!='little':values.byteswap()
        if min(values)<1 or max(values)>65535:raise ValueError('probability')
        data=json.loads(r.take(n));r.end()
        if len(data)!=(3 if state else 2):raise ValueError('snapshot sections')
        m.probs=values;m.tables=untyped(data[0]);m.tidx={k:{v:i for i,v in enumerate(vs)} for k,vs in m.tables.items()};m.ema=untyped(data[1]);m.last=untyped(data[2]) if state else {};m.table_bytes=sum(len(v.encode('utf-8','surrogatepass')) for vs in m.tables.values() for v in vs);m.table_entries=sum(len(vs) for vs in m.tables.values());m.check_budget();return m
    def state_id(self):return hashlib.blake2s(self.snapshot(True),digest_size=16,person=b'MTB5state'[:8]).digest()
    def artifact(self):return zlib.compress(self.snapshot(),9)

def load_artifact(blob,expected_sha256):
    if len(blob)>1048576 or hashlib.sha256(blob).hexdigest()!=expected_sha256:raise ValueError('prior asset identity')
    dec=zlib.decompressobj();raw=dec.decompress(blob,6*MAX_TABLE_BYTES+1)
    if len(raw)>6*MAX_TABLE_BYTES or not dec.eof or dec.unused_data or dec.unconsumed_tail:raise ValueError('prior asset limits')
    return Model.restore(raw)
