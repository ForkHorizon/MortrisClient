"""Bounded reference integer/float streams; no product integration."""
import math, struct
U64=(1<<64)-1

def u(v):
    if type(v) is not int or not 0<=v<=U64:raise ValueError('uint64')
    out=bytearray()
    while v>=128:out.append((v&127)|128);v>>=7
    out.append(v);return bytes(out)
def zz(v):
    if not -(1<<63)<=v<(1<<63):raise ValueError('int64')
    return (v<<1)^(v>>63)
def packbits(xs,w):
    if not 0<=w<=64:raise ValueError('width')
    acc=bits=0;out=bytearray()
    for x in xs:
        if not 0<=x<(1<<w):raise ValueError('bit value')
        acc|=x<<bits;bits+=w
        while bits>=8:out.append(acc&255);acc>>=8;bits-=8
    if bits:out.append(acc)
    return bytes(out)
class Reader:
    def __init__(self,b):self.b=memoryview(b);self.p=0
    def take(self,n):
        if n<0 or n>len(self.b)-self.p:raise ValueError('truncated')
        out=self.b[self.p:self.p+n];self.p+=n;return bytes(out)
    def byte(self):return self.take(1)[0]
    def u(self):
        v=0
        for i in range(10):
            b=self.byte()
            if i==9 and b>1:raise ValueError('u64 overflow')
            v|=(b&127)<<(7*i)
            if b<128:
                if i and b==0:raise ValueError('overlong')
                return v
        raise ValueError('long varint')
    def s(self):
        v=self.u();return (v>>1)^-(v&1)
    def count(self,limit):
        n=self.u()
        if n>limit:raise ValueError('count limit')
        return n
    def end(self):
        if self.p!=len(self.b):raise ValueError('trailing')
def readbits(r,n,w):
    if not 0<=w<=64 or not 0<=n<=16000:raise ValueError('bit dimensions')
    raw=r.take((n*w+7)//8);acc=int.from_bytes(raw,'little')
    if acc>>(n*w):raise ValueError('nonzero padding')
    mask=(1<<w)-1;return [(acc>>(i*w))&mask for i in range(n)]
def ints(xs,advanced=True,ef=True):
    """Candidate sizes include mode and metadata; compressed size measured elsewhere."""
    if not xs:return b''
    opts=[]
    for mode,vs in [(0,xs),(1,[xs[0]]+[b-a for a,b in zip(xs,xs[1:])])]:
        try:opts.append(bytes([mode])+b''.join(u(zz(v)) for v in vs))
        except ValueError:pass
        if advanced:
            lo=min(vs);w=(max(vs)-lo).bit_length()
            if -(1<<63)<=lo<(1<<63) and w<=64:opts.append(bytes([mode+2])+u(zz(lo))+bytes([w])+packbits([v-lo for v in vs],w))
    if advanced and ef and all(a<=b for a,b in zip(xs,xs[1:])):
        lo=xs[0];span=xs[-1]-lo;l=max(0,(span//len(xs)).bit_length()-1)
        high=[(v-lo)>>l for v in xs];hn=high[-1]+len(xs)+1
        if -(1<<63)<=lo<(1<<63) and hn<=32000:
            bits=bytearray((hn+7)//8)
            for i,h in enumerate(high):bits[(h+i)//8]|=1<<((h+i)%8)
            opts.append(b'\x04'+u(zz(lo))+bytes([l])+u(hn)+packbits([(v-lo)&((1<<l)-1) for v in xs],l)+bits)
    if not opts:raise ValueError('integer domain')
    return min(opts,key=len)
def readints(r,n):
    if not n:return []
    mode=r.byte()
    if mode in (0,1):out=[r.s() for _ in range(n)]
    elif mode in (2,3):
        lo=r.s();out=[lo+x for x in readbits(r,n,r.byte())]
    elif mode==4:
        lo=r.s();l=r.byte();hn=r.count(32000);low=readbits(r,n,l);bits=r.take((hn+7)//8)
        high=[i for i in range(hn) if bits[i//8]>>(i%8)&1]
        if len(high)!=n or (int.from_bytes(bits,'little')>>hn):raise ValueError('EF high')
        return [lo+((h-i)<<l)+v for i,(h,v) in enumerate(zip(high,low))]
    else:raise ValueError('integer mode')
    if mode in (1,3):
        total=0
        for i,v in enumerate(out):total+=v;out[i]=total
    return out

def floats(xs,size,advanced):
    fmt='<f' if size==4 else '<d';opts=[b'\x00'+b''.join(struct.pack(fmt,x) for x in xs)]
    if advanced:
        # Decimal scaling: accept only exact binary and signed-zero restoration.
        for scale in range(10):
            factor=10**scale;ms=[]
            for x in xs:
                y=x*factor
                if not math.isfinite(y) or abs(y)>=(1<<63):break
                m=round(y)
                if struct.pack(fmt,m/factor)!=struct.pack(fmt,x):break
                ms.append(m)
            if len(ms)==len(xs):opts.append(b'\x01'+bytes([scale])+ints(ms))
        # XOR with leading AND trailing zero byte stripping; not Chimp128.
        out=bytearray(b'\x02');prev=0
        for x in xs:
            v=int.from_bytes(struct.pack(fmt,x),'little');delta=v^prev;prev=v
            if not delta:out.append(0);continue
            low=(delta&-delta).bit_length()-1;tz=low//8;nb=(delta.bit_length()+7)//8-tz
            out.append((tz<<4)|nb);out+=delta.to_bytes(size,'little')[tz:tz+nb]
        opts.append(bytes(out))
    return min(opts,key=len)
def readfloats(r,n,size):
    fmt='<f' if size==4 else '<d';mode=r.byte()
    if mode==0:out=[struct.unpack(fmt,r.take(size))[0] for _ in range(n)]
    elif mode==1:
        scale=r.byte()
        if scale>9:raise ValueError('float scale')
        out=[struct.unpack(fmt,struct.pack(fmt,v/10**scale))[0] for v in readints(r,n)]
    elif mode==2:
        prev=0;out=[]
        for _ in range(n):
            h=r.byte();tz=h>>4;nb=h&15
            if tz+nb>size or (not nb and tz):raise ValueError('xor span')
            prev^=int.from_bytes(r.take(nb),'little')<<(8*tz);out.append(struct.unpack(fmt,prev.to_bytes(size,'little'))[0])
    else:raise ValueError('float mode')
    if not all(math.isfinite(x) for x in out):raise ValueError('nonfinite')
    return out
