"""Exact source-byte overlay. Experimental escape, not a lossy normalization."""
import difflib,json,hashlib
from types import SimpleNamespace
from primitives import Reader,u
import core,wire

def render(inst,events):
    try:return wire.v1_json(inst,events,True)
    except UnicodeEncodeError:
        # Internal WTF-8 strings are rendered as valid escaped JSON bytes.
        obj=wire._v1_obj(inst,events)
        for e in obj['events']:e.pop('event_id',None)
        return wire.jdump(obj).encode('utf-8',errors='backslashreplace')
def overlay(base,source):
    if base==source:return b'\x00'
    if max(len(base),len(source))>2097152:raise ValueError('source length')
    # Limit expensive matching to unusual source bytes; never part of normal core path.
    edits=[(a,b,source[c:d]) for op,a,b,c,d in difflib.SequenceMatcher(None,base,source,autojunk=False).get_opcodes() if op!='equal']
    return b'\x01'+u(len(source))+u(len(edits))+b''.join(u(a)+u(b-a)+u(len(v))+v for a,b,v in edits)
def apply(base,patch):
    r=Reader(patch);kind=r.byte()
    if kind==0:r.end();return base
    if kind!=1:raise ValueError('patch kind')
    total=r.count(2097152);count=r.count(16000);out=bytearray();prev=0
    for _ in range(count):
        a=r.u();deleted=r.u();inserted=r.count(2097152)
        if a<prev or a+deleted>len(base):raise ValueError('patch span')
        if len(out)+a-prev+inserted>total:raise ValueError('patch output')
        out+=base[prev:a];out+=r.take(inserted);prev=a+deleted
    if len(out)+len(base)-prev!=total:raise ValueError('patch length')
    out+=base[prev:];r.end();return bytes(out)
def encode(inst,batch,source=None,**kwargs):
    raw,tail=core.encode(inst,batch,**kwargs);meta,ev=core.decode(raw,tail);base=render(inst,ev)
    source=render(inst,batch) if source is None else source
    patch=overlay(base,source)
    return u(len(raw))+raw+patch,tail

def decode(raw,tail):
    r=Reader(raw);core_raw=r.take(r.count(2097152));meta,ev=core.decode(core_raw,tail)
    base=render(SimpleNamespace(install_id=meta['install_id']),ev)
    return apply(base,r.take(len(raw)-r.p)),meta,ev

class Lexeme(str):pass
class Pairs(list):pass
def _pairs(xs):
    keys=[k for k,_ in xs]
    if len(set(keys))!=len(keys):raise ValueError('duplicate key')
    return Pairs(xs)
def canonical_event(source):
    obj=json.loads(source,parse_int=Lexeme,parse_float=Lexeme,object_pairs_hook=_pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite')))
    if not isinstance(obj,Pairs):raise ValueError('event object')
    def emit(v):
        if isinstance(v,Lexeme):return str(v)
        if isinstance(v,Pairs):return '{'+','.join(json.dumps(k,ensure_ascii=True)+':'+emit(x) for k,x in v)+'}'
        if isinstance(v,list):return '['+','.join(emit(x) for x in v)+']'
        return json.dumps(v,ensure_ascii=True,separators=(',',':'))
    return emit(Pairs((k,v) for k,v in obj if k!='event_id')).encode('ascii')
def digest(project,origin,source):
    # Length-prefixed complete identity and canonical event prevent separator ambiguity.
    parts=[b'MTB4-event-v1',project.encode(),origin.encode(),canonical_event(source)]
    return hashlib.sha256(b''.join(u(len(p))+p for p in parts)).digest()
