"""Binary adaptive range coder (LZMA-style carry handling), 16-bit probabilities, two-rate mixing.
Encoder cost per binary decision: 1 multiply, a few adds/shifts, occasional byte output. Easy to port to C#."""
PB=16; ONE=1<<PB; TOP=1<<24; MASK32=0xFFFFFFFF
FAST,SLOW=4,7
class Enc:
    __slots__=('low','range','cache','csize','out','nbits')
    def __init__(s):s.low=0;s.range=MASK32;s.cache=0;s.csize=1;s.out=bytearray();s.nbits=0
    def _shift(s):
        if s.low<0xFF000000 or s.low>MASK32:
            carry=s.low>>32;t=s.cache
            while True:
                s.out.append((t+carry)&0xFF);t=0xFF;s.csize-=1
                if not s.csize:break
            s.cache=(s.low>>24)&0xFF
        s.csize+=1;s.low=(s.low&0x00FFFFFF)<<8
    def bit(s,pr,b):
        # pr: [p_fast,p_slow] probability of bit==0 in 16 bits
        p=(pr[0]+pr[1])>>1
        if p<32:p=32
        elif p>ONE-32:p=ONE-32
        bound=(s.range>>PB)*p;s.nbits+=1
        if b:s.low+=bound;s.range-=bound;pr[0]-=pr[0]>>FAST;pr[1]-=pr[1]>>SLOW
        else:s.range=bound;pr[0]+=(ONE-pr[0])>>FAST;pr[1]+=(ONE-pr[1])>>SLOW
        while s.range<TOP:s.range<<=8;s._shift()
        return b
    def finish(s):
        # choose a value inside [low,low+range) with most trailing zero bits, then drop zero tail (decoder pads 0)
        lo,hi=s.low,s.low+s.range-1
        for k in range(32,-1,-1):
            m=(1<<k)-1;v=(lo+m)&~m
            if v<=hi:break
        s.low=v
        for _ in range(5):s._shift()
        out=bytes(s.out[1:])  # first byte is always the initial cache 0
        return out.rstrip(b'\x00')
class Dec:
    __slots__=('buf','pos','range','code','nbits')
    def __init__(s,buf):
        s.buf=buf;s.pos=0;s.range=MASK32;s.code=0;s.nbits=0
        for _ in range(4):s.code=(s.code<<8)|s._byte()
    def _byte(s):
        if s.pos<len(s.buf):b=s.buf[s.pos]
        else:b=0
        s.pos+=1;return b
    def bit(s,pr,_=None):
        p=(pr[0]+pr[1])>>1
        if p<32:p=32
        elif p>ONE-32:p=ONE-32
        bound=(s.range>>PB)*p;s.nbits+=1
        if s.code>=bound:s.code-=bound;s.range-=bound;pr[0]-=pr[0]>>FAST;pr[1]-=pr[1]>>SLOW;b=1
        else:s.range=bound;pr[0]+=(ONE-pr[0])>>FAST;pr[1]+=(ONE-pr[1])>>SLOW;b=0
        while s.range<TOP:s.range=(s.range<<8)&MASK32;s.code=((s.code<<8)|s._byte())&MASK32
        return b
