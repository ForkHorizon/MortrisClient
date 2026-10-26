"""Evidence only: integer arithmetic coder with trained byte-context priors.
32-bit arithmetic coding, E1/E2/E3 renormalization, adaptive counts rescale at 16384.
Streams are field-conditioned; previous-byte context and optional previous event type.
"""
from collections import Counter
import bisect
TOP=1<<32; HALF=1<<31; Q=1<<30
class Bits:
    def __init__(self,data=None):self.bits=[];self.data=data;self.p=0
    def put(self,b):self.bits.append(b)
    def get(self):
        p=self.p;self.p+=1
        return (self.data[p//8]>>(7-p%8))&1 if p//8<len(self.data) else 0
    def finish(self):
        b=bytearray((len(self.bits)+7)//8)
        for i,x in enumerate(self.bits):b[i//8]|=x<<(7-i%8)
        return bytes(b)
def frequencies(prior):
    c=[1]*256
    for x,n in (prior or {}).items():c[x]+=min(60,n)
    return c

def code(streams,priors=None,decode=None,lengths=None):
    # One arithmetic stream across all fields; models reset at each batch.
    models={}; lo=0; hi=TOP-1;pending=0; bits=Bits(decode); value=0
    if decode is not None:
        for _ in range(32):value=(value<<1)|bits.get()
    def emit(b):
        nonlocal pending
        bits.put(b)
        for _ in range(pending):bits.put(1-b)
        pending=0
    result=[]
    for j,source in enumerate(streams):
        prev=256; dest=bytearray(); n=lengths[j] if decode is not None else len(source)
        for i in range(n):
            ctx=(j,prev)
            if ctx not in models:models[ctx]=frequencies((priors or {}).get(ctx))
            c=models[ctx]; cum=[0]
            for f in c:cum.append(cum[-1]+f)
            total=cum[-1]; width=hi-lo+1
            if decode is None:symbol=source[i]
            else:
                target=((value-lo+1)*total-1)//width
                symbol=bisect.bisect_right(cum,target)-1
            hi=lo+width*cum[symbol+1]//total-1;lo=lo+width*cum[symbol]//total
            while True:
                if hi<HALF:
                    if decode is None:emit(0)
                elif lo>=HALF:
                    if decode is None:emit(1)
                    lo-=HALF;hi-=HALF
                    if decode is not None:value-=HALF
                elif lo>=Q and hi<3*Q:
                    if decode is None:pending+=1
                    lo-=Q;hi-=Q
                    if decode is not None:value-=Q
                else:break
                lo=lo*2;hi=hi*2+1
                if decode is not None:value=value*2+bits.get()
            c[symbol]+=1
            if sum(c)>=16384:c[:]=[max(1,(x+1)//2) for x in c]
            dest.append(symbol);prev=symbol
        result.append(bytes(dest))
    if decode is None:
        pending+=1;emit(0 if lo<Q else 1)
        return bits.finish()
    return result

def selfcheck():
    import random
    r=random.Random(77)
    for n in (0,1,10,1000):
        streams=[r.randbytes(n),b'abcd'*n]
        c=code(streams);assert code([b'',b''],decode=c,lengths=list(map(len,streams)))==streams
if __name__=='__main__':selfcheck();print('arithmetic roundtrip OK')
