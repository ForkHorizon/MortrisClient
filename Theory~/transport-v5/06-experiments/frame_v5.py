"""Guarded research request codec. All operations return candidate state; caller commits on ACK."""
import json,struct,uuid,zlib,time,re
from decimal import Decimal,DecimalException
from types import SimpleNamespace
from datetime import datetime,timezone
from support import Reader,u,exact,wire
from model import Model
from context_codec import Coder,code_batch
MAX_FRAME=262144;MAX_SOURCE=2097152

def render(origin,events,sent_delta=250):
    body=exact.render(SimpleNamespace(install_id=origin),events)
    if sent_delta!=250:
        from gen import iso_ms
        old=json.dumps(iso_ms(events[-1]['ts']+250)).encode();new=json.dumps(iso_ms(events[-1]['ts']+sent_delta)).encode()
        needle=b'"sent_at_client":'+old
        if body.count(needle)!=1:raise ValueError('sent field')
        body=body.replace(needle,b'"sent_at_client":'+new,1)
    return body

def source_info(source,origin,n):
    if not 0<len(source)<=MAX_SOURCE:raise ValueError('source size')
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise ValueError('duplicate key')
            d[k]=v
        return d
    obj=json.loads(source,object_pairs_hook=pairs,parse_float=exact.Lexeme,parse_int=exact.Lexeme,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite')))
    if not isinstance(obj,dict) or obj.get('install_id')!=origin or obj.get('project_id')!=wire.PROJECT_ID:raise ValueError('origin/project')
    ev=obj.get('events')
    if not isinstance(ev,list) or len(ev)!=n:raise ValueError('source events')
    if not isinstance(obj.get('schema_version'),exact.Lexeme) or obj.get('schema_version')!='1' or not isinstance(obj.get('sdk'),dict) or any(type(obj['sdk'].get(k)) is not str for k in ('name','version')):raise ValueError('source envelope')
    seqs=[]
    for e in ev:
        if not isinstance(e,dict):raise ValueError('source event')
        s=e.get('sequence')
        if not isinstance(s,exact.Lexeme) or not str(s).isdigit() or not 1<=int(s)<(1<<63):raise ValueError('source sequence')
        seqs.append(int(s))
        name=e.get('name');props=e.get('properties')
        if type(name) is not str or len(name)>64 or not re.fullmatch(r'[a-z](?:[a-z0-9]|_(?!_))*[a-z0-9]|[a-z]',name):raise ValueError('source name')
        if not isinstance(props,dict) or len(props)>32:raise ValueError('source properties')
        for key,value in props.items():
            if len(key)>64 or not re.fullmatch(r'[a-z](?:[a-z0-9]|_(?!_))*[a-z0-9]|[a-z]',key):raise ValueError('source key')
            if isinstance(value,exact.Lexeme):
                try:number=Decimal(value)
                except DecimalException as ex:raise ValueError('source numeric') from ex
                if not number.is_finite() or number.copy_abs()>Decimal('1.7976931348623157e308'):raise ValueError('source numeric domain')
            elif type(value) is str:
                if len(value.encode('utf-8',errors='replace'))>1024:raise ValueError('source string')
            elif value is not None and type(value) is not bool:raise ValueError('source property type')
        def proptext(value):
            if isinstance(value,exact.Lexeme):return str(value)
            return json.dumps(value,ensure_ascii=False,separators=(',',':'))
        serialized='{'+','.join(json.dumps(k)+':'+proptext(v) for k,v in props.items())+'}'
        serialized=serialized.replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
        if len(serialized.encode('utf-8',errors='backslashreplace'))>8192:raise ValueError('source property bytes')
        for key in ('session_id','occurred_at_client',*wire.DEVICE_KEYS[:-1]):
            if type(e.get(key)) is not str:raise ValueError('source context type')
        for key in ('session_elapsed_ms','timezone_offset_minutes'):
            v=e.get(key)
            if not isinstance(v,exact.Lexeme) or not re.fullmatch(r'-?[0-9]+',str(v)):raise ValueError('source context number')
            limit=63 if key=='session_elapsed_ms' else 31
            if not -(1<<limit)<=int(v)<(1<<limit):raise ValueError('source context range')
        if str(uuid.UUID(e['session_id']))!=e['session_id']:raise ValueError('source session')
        ts=e['occurred_at_client']
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z',ts):raise ValueError('source time format')
        datetime.strptime(ts,'%Y-%m-%dT%H:%M:%S.%fZ')
    if any(a>=b for a,b in zip(seqs,seqs[1:])):raise ValueError('source sequence order')
    return obj

def sent_delta_from_source(source,origin,events):
    obj=source_info(source,origin,len(events));text=obj['sent_at_client']
    if [int(e['sequence']) for e in obj['events']]!=[e['sequence'] for e in events]:raise ValueError('source identity mismatch')
    dt=datetime.strptime(text,'%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)
    epoch=datetime(1970,1,1,tzinfo=timezone.utc);delta=dt-epoch
    return delta.days*86400000+delta.seconds*1000+delta.microseconds//1000-events[-1]['ts']

def encode(prior,origin,batch,*,base=None,source=None,model_id=1,hash_rule=False):
    if not 1<=len(batch)<=500 or not 1<=model_id<=127:raise ValueError('encode limits')
    if str(uuid.UUID(origin))!=origin:raise ValueError('origin uuid')
    source=render(origin,batch) if source is None else source
    sent=sent_delta_from_source(source,origin,batch)
    # Build only a candidate: failure, timeout or malformed ACK cannot change the live model.
    m=(base if base is not None else prior).clone()
    if base is None:m.reset_batch_state()
    elif m.last.get(('install',),origin)!=origin:raise ValueError('state origin')
    m.last[('install',)]=origin
    c=Coder(m,True);c.expected_events=len(batch);c.sent_delta=sent;c.max_literal_bytes=min(4194304,8192+2*len(source));c.max_decisions=min(20000000,8192+len(source)*16)
    code_batch(c,origin,batch,True,hash_rule)
    canonical=render(origin,batch,sent);patch=exact.overlay(canonical,source);flags=int(patch!=b'\x00')|(int(hash_rule)<<1)
    if flags&1:c.bytes_o1(('source_overlay',),patch)
    body=c.rc.finish();kind=2 if base is not None else 1
    frame=bytes([0x50|kind,flags])+u(model_id)+u(len(batch))+u(len(source))+uuid.UUID(origin).bytes
    if base is not None:frame+=base.state_id()
    frame+=body+struct.pack('<I',zlib.crc32(source))
    if len(frame)>MAX_FRAME:raise ValueError('split or V4/V1 fallback')
    return frame,m

def decode(prior,frame,*,base=None,model_id=1,timeout_seconds=5.0):
    if not 24<=len(frame)<=MAX_FRAME:raise ValueError('frame size')
    r=Reader(frame);header=r.byte();flags=r.byte()
    if header not in (0x51,0x52) or flags&~3:raise ValueError('header')
    if r.count(127)!=model_id:raise ValueError('model id')
    n=r.count(500);size=r.count(MAX_SOURCE);origin=str(uuid.UUID(bytes=r.take(16)))
    if not n or not size:raise ValueError('limits')
    if header==0x52:
        ref=r.take(16)
        if base is None or base.state_id()!=ref:raise ValueError('missing/mismatched base')
        if base.last.get(('install',),origin)!=origin:raise ValueError('state origin')
    elif base is not None:raise ValueError('unexpected base')
    if len(frame)-r.p<4:raise ValueError('CRC')
    body=r.take(len(frame)-r.p-4);checksum=r.take(4);m=(base if base is not None else prior).clone()
    if base is None:m.reset_batch_state()
    m.last[('install',)]=origin
    c=Coder(m,False,body);c.deadline=time.monotonic()+timeout_seconds;c.expected_events=n;c.max_literal_bytes=min(4194304,8192+2*size);c.max_decisions=min(20000000,8192+size*16)
    iid,events=code_batch(c,origin,None,True,bool(flags&2));source=render(origin,events,c.sent_delta)
    if flags&1:source=exact.apply(source,c.bytes_o1(('source_overlay',)))
    # Re-emit decisions while decoding: reject extra/truncated/noncanonical range streams.
    if c.shadow.finish()!=body:raise ValueError('noncanonical range stream')
    if len(source)!=size or zlib.crc32(source)!=struct.unpack('<I',checksum)[0]:raise ValueError('source length/CRC')
    info=source_info(source,origin,n)
    if [int(e['sequence']) for e in info['events']]!=[e['sequence'] for e in events]:raise ValueError('source identity mismatch')
    return source,m
