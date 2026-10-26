"""Lossless generic integer-column candidates; no project-specific names/rules."""
from support7 import v6,Reader
MIN,MAX=-(1<<63),(1<<63)-1
BASES={1:'ts',2:'sequence',3:'session_elapsed_ms'}

def options(values,owners):
    result={0:v6.integers(values)}
    for mode,key in BASES.items():
        residual=[v-e[key]for v,e in zip(values,owners)]
        if all(MIN<=v<=MAX for v in residual):result[mode]=v6.integers(residual)
    unique=list(dict.fromkeys(values));ids={v:i for i,v in enumerate(unique)}
    result[4]=v6.u(len(unique))+v6.integers(unique)+v6.integers([ids[v]for v in values])
    return result

def encode(values,owners):
    choices=options(values,owners)
    mode=min(choices,key=lambda m:(len(choices[m]),m))
    return bytes([mode])+choices[mode]

def decode(reader,n,owners):
    mode=reader.byte()
    if mode==4:
        count=reader.count(n)
        if not count:raise ValueError('empty integer dictionary')
        unique=v6.readintegers(reader,count)
        indices=v6.readintegers(reader,n)
        if any(not 0<=i<count for i in indices):raise ValueError('integer dictionary index')
        values=[unique[i]for i in indices]
    elif mode in (0,*BASES):
        values=v6.readintegers(reader,n)
        if mode:
            values=[v+e[BASES[mode]]for v,e in zip(values,owners)]
    else:raise ValueError('integer prediction mode')
    if any(not MIN<=v<=MAX for v in values):raise ValueError('integer prediction overflow')
    return values
