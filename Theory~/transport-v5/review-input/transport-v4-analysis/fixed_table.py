"""C#-style fixed context table: index = hash(ctx) & (slots-1), no key check (collisions shared by encoder
and decoder, so still lossless). Memory = slots * 4 bytes (two uint16 probabilities)."""
import sys,json
import ctxcodec as cc,rc
from evalctx import train,evaluate
class FixedCoder(cc.Coder):
    MASK=None
    def bit(s,ctx,b=None):
        k=hash(ctx)&FixedCoder.MASK;pr=s.P.get(k)
        if pr is None:pr=s.P[k]=[32768,32768]
        return s.rc.bit(pr,b)
cc.Coder.bit=FixedCoder.bit
rows=[]
for name in sys.argv[1:]:
    for bits in (14,16,18):
        FixedCoder.MASK=(1<<bits)-1
        snap=train(name,100)
        for sf in (False,True):
            r=evaluate(name,'test101',100,snap,stateful=sf);r['slots']=1<<bits;r['table_bytes']=4<<bits;r['used_slots']=len(snap.probs)
            print(r,flush=True);rows.append(r)
json.dump(rows,open('results/fixed_table_'+'_'.join(sys.argv[1:])+'.json','w'),indent=1)
