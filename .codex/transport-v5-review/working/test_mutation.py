"""Decoder must reject or bound garbage: random mutations of real frames, each decode must finish quickly."""
import random,time
from common import *
import ctxcodec as cc
from evalctx import train
snap=train('base',100);te=workload('base','test101',100);rng=random.Random(9);frames=[]
for inst,bs in te[:2]:
    for b in bs[:10]:frames.append(cc.encode(snap.clone(),inst.install_id,b)[0])
stats={'rejected':0,'decoded':0};worst=0
for i in range(2000):
    f=bytearray(rng.choice(frames));op=rng.randrange(3)
    if op==0:
        for _ in range(rng.randrange(1,4)):f[rng.randrange(1,len(f))]^=1<<rng.randrange(8)
    elif op==1:f=f[:rng.randrange(1,len(f))]
    else:f=f[:1]+bytes(rng.randrange(256) for _ in range(rng.randrange(1,300)))
    t0=time.perf_counter()
    try:cc.decode(snap.clone(),bytes(f));stats['decoded']+=1
    except (ValueError,UnicodeDecodeError,OverflowError) as ex:stats['rejected']+=1
    worst=max(worst,time.perf_counter()-t0)
print(stats,'worst decode s',round(worst,3))
