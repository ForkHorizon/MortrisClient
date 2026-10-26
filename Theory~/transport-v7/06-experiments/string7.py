"""Generic exact UTF-8 distinct-table prefix/suffix coding; no CSV/game semantics."""
from decimal import Decimal
import uuid
from support7 import v6,core
MAX_TABLE=2097152

def encode(t,values):
    if t not in (core.T_STR,core.T_NUMTEXT):raise ValueError('string model type')
    texts=[str(v)for v in values];unique=list(dict.fromkeys(texts));ids={v:i for i,v in enumerate(unique)}
    previous=b'';prefixes=[];suffixes=[];middles=[];total=0;limit=1024 if t==core.T_STR else 8192
    for text in unique:
        current=text.encode('utf-8',errors='surrogatepass');total+=len(current)
        if len(current)>limit or total>MAX_TABLE:raise ValueError('string table budget')
        p=s=0
        while p<min(len(previous),len(current))and previous[p]==current[p]:p+=1
        while s<min(len(previous)-p,len(current)-p)and previous[-s-1]==current[-s-1]:s+=1
        prefixes.append(p);suffixes.append(s);middles.append(current[p:len(current)-s if s else len(current)]);previous=current
    payload=v6.u(len(unique))+v6.integers(prefixes)+v6.integers(suffixes)+b''.join(v6.blob(b)for b in middles)+v6.integers([ids[v]for v in texts])
    candidates=[b'\x00'+v6.enc_values(t,values),b'\x01'+payload]
    if t==core.T_STR:
        tagged=[];tags=[]
        for text in unique:
            tag=0;value=text.encode('utf-8',errors='surrogatepass')
            try:
                ident=uuid.UUID(text)
                if str(ident)==text:tag=1;value=ident.bytes
            except (ValueError,AttributeError):pass
            if not tag and text and len(text)%2==0:
                try:
                    binary=bytes.fromhex(text)
                    if binary.hex()==text:tag=2;value=binary
                except ValueError:pass
            tags.append(tag);tagged.append(bytes([tag])+(value if tag==1 else v6.blob(value)))
        indices=v6.integers([ids[v]for v in texts])
        if all(t==1 for t in tags):candidates.append(b'\x02'+v6.enc_values(core.T_UUID,values))
        if all(t==2 for t in tags):candidates.append(b'\x03'+v6.enc_values(core.T_HEX,values))
        candidates.append(b'\x04'+v6.u(len(unique))+b''.join(tagged)+indices)
    return min(candidates,key=len)

def decode(r,t,n):
    mode=r.byte()
    if mode==0:return v6.dec_values(r,t,n)
    if mode in (2,3):
        if t!=core.T_STR:raise ValueError('binary string type')
        return v6.dec_values(r,core.T_UUID if mode==2 else core.T_HEX,n)
    if mode==4:
        if t!=core.T_STR:raise ValueError('binary string type')
        count=r.count(n);unique=[]
        if not count:raise ValueError('empty string table')
        for _ in range(count):
            tag=r.byte()
            if tag==0:value=r.take(r.count(1024)).decode('utf-8',errors='surrogatepass')
            elif tag==1:value=str(uuid.UUID(bytes=r.take(16)))
            elif tag==2:value=r.take(r.count(512)).hex()
            else:raise ValueError('binary string tag')
            unique.append(value)
        indices=v6.readintegers(r,n)
        if any(not 0<=i<count for i in indices):raise ValueError('string table index')
        return [unique[i]for i in indices]
    if mode!=1:raise ValueError('string model mode')
    count=r.count(n)
    if not count:raise ValueError('empty string table')
    prefixes=v6.readintegers(r,count);suffixes=v6.readintegers(r,count)
    previous=b'';unique=[];total=0;limit=1024 if t==core.T_STR else 8192
    for p,s in zip(prefixes,suffixes):
        if p<0 or s<0 or p+s>len(previous):raise ValueError('string reference range')
        middle=r.take(r.count(limit))
        if p+s+len(middle)>limit:raise ValueError('expanded string limit')
        current=previous[:p]+middle+(previous[-s:]if s else b'');total+=len(current)
        if total>MAX_TABLE:raise ValueError('expanded string table budget')
        value=current.decode('utf-8',errors='surrogatepass')
        if t==core.T_NUMTEXT:
            value=Decimal(value)
            if not value.is_finite():raise ValueError('decimal')
        unique.append(value);previous=current
    indices=v6.readintegers(r,n)
    if any(not 0<=i<count for i in indices):raise ValueError('string table index')
    return [unique[i]for i in indices]
