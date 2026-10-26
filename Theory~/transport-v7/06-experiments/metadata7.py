"""Bounded signed integer metadata coding with exact direct/delta value tables."""
from support7 import v6
MIN,MAX=-(1<<63),(1<<63)-1

def table(values):
    unique=list(dict.fromkeys(values));indices={v:i for i,v in enumerate(unique)}
    return v6.u(len(unique))+v6.integers(unique)+v6.integers([indices[v]for v in values])

def encode(values):
    candidates=[v6.integers(values),b'\x04'+table(values)]
    delta=[values[0]]+[b-a for a,b in zip(values,values[1:])]
    if all(MIN<=v<=MAX for v in delta):candidates.append(b'\x05'+table(delta))
    return min(candidates,key=len)

def decode(r,n):
    if r.p>=len(r.b):raise ValueError("truncated metadata")
    mode=r.b[r.p]
    if mode<4:return v6.readintegers(r,n)
    r.byte()
    if mode not in (4,5):raise ValueError('metadata mode')
    count=r.count(n)
    if not count:raise ValueError('metadata dictionary count')
    unique=v6.readintegers(r,count);indices=v6.readintegers(r,n)
    if any(not 0<=i<count for i in indices):raise ValueError('metadata dictionary index')
    values=[unique[i]for i in indices]
    if mode==5:
        for i in range(1,n):values[i]+=values[i-1]
    if any(not MIN<=v<=MAX for v in values):raise ValueError('metadata overflow')
    return values
