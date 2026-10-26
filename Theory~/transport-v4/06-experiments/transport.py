"""Research full request path: original source -> framed codec -> exact original bytes."""
from types import SimpleNamespace
from primitives import u
import core,exact,framing

def encode(inst,batch,source=None,d=None,level=9,**opts):
    source=exact.render(inst,batch) if source is None else source
    try:
        raw,tail=core.encode(inst,batch,**opts);meta,ev=core.decode(raw,tail);base=exact.render(inst,ev)
        if base==source:return framing.pack(raw,tail,len(batch),d,1 if d is not None else 0,level,kind=1)
        raw=u(len(raw))+raw+exact.overlay(base,source)
        f=framing.pack(raw,tail,len(batch),d,1 if d is not None else 0,level,kind=2)
        literal=framing.pack(source,b'',len(batch),d,1 if d is not None else 0,level,kind=0)
        return min((f,literal),key=len)
    except (ValueError,UnicodeError,OverflowError):
        # Caller retains queue and falls back to existing V1 if this also exceeds negotiated limits.
        return framing.pack(source,b'',len(batch),d,1 if d is not None else 0,level,kind=0)

def decode(frame,dicts):
    kind,raw,tail,n=framing.unpack(frame,dicts)
    if kind==0:
        if tail:raise ValueError('literal trailer')
        return raw
    if kind==2:
        source,meta,ev=exact.decode(raw,tail)
    else:
        meta,ev=core.decode(raw,tail);source=exact.render(SimpleNamespace(install_id=meta['install_id']),ev)
    if n!=len(ev):raise ValueError('outer/core event count')
    return source
