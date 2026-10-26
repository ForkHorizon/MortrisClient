"""Experimental exact signed-int cross-column residuals; no project semantics.
Raw-column experiment only: not yet a negotiated M7 flag or native implementation.
"""
from collections import Counter
from support7 import Reader,v6,core
import numeric7,string7

MAX_REFS=16

def encode(values,owners,rows,previous):
    best=numeric7.encode(values,owners)
    for distance,source in enumerate(reversed(previous[-MAX_REFS:]),1):
        basis=[source.get(i,0)for i in rows]
        for mode in (5,6):
            residual=[v-b if mode==5 else v+b for v,b in zip(values,basis)]
            if not all(numeric7.MIN<=v<=numeric7.MAX for v in residual):continue
            candidate=bytes([mode])+v6.u(distance)+v6.integers(residual)
            if len(candidate)<len(best):best=candidate
    return best

def decode(r,n,owners,rows,previous):
    if r.p>=len(r.b):raise ValueError('truncated cross column')
    if r.b[r.p]<5:return numeric7.decode(r,n,owners)
    mode=r.byte()
    if mode not in (5,6):raise ValueError('cross mode')
    distance=r.count(MAX_REFS)
    if not 1<=distance<=len(previous):raise ValueError('cross reference')
    source=previous[-distance];residual=v6.readintegers(r,n)
    values=[v+source.get(i,0)if mode==5 else v-source.get(i,0)for v,i in zip(residual,rows)]
    if any(not numeric7.MIN<=v<=numeric7.MAX for v in values):raise ValueError('cross overflow')
    return values

def rewrite(raw,catalog,batch,preserve_ids=False,cross_input=False):
    """Convert numeric+string raw columns to/from cross columns; assert every value."""
    r=Reader(raw);n=len(batch)
    for _ in range(5):v6.readintegers(r,n)
    if preserve_ids:r.take(n*16)
    out=bytearray(raw[:r.p]);columns={};previous=[];modes=Counter()
    for i,e in enumerate(batch):
        for k,t in catalog.shapes[catalog.ids[catalog.shape(e)]][1]:columns.setdefault((k,t),[]).append(i)
    for (key,t),rows in columns.items():
        owners=[batch[i]for i in rows];start=r.p
        if t==core.T_INT:
            values=decode(r,len(rows),owners,rows,previous)if cross_input else numeric7.decode(r,len(rows),owners)
            payload=numeric7.encode(values,owners)if cross_input else encode(values,owners,rows,previous)
            modes[payload[0]]+=1;out+=payload
            previous.append(dict(zip(rows,values)))
            if len(previous)>MAX_REFS:previous.pop(0)
        else:
            values=string7.decode(r,t,len(rows))if t in (core.T_STR,core.T_NUMTEXT)else v6.dec_values(r,t,len(rows))
            out+=raw[start:r.p]
        assert values==[e['properties'][key]for e in owners],key
    r.end()
    return bytes(out),modes
