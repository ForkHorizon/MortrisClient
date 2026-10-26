"""Lossless roundtrip tests for MTB5 (stateless+stateful) on edge cases + fuzzed random events."""
import random,struct,uuid,sys
from decimal import Decimal
from types import SimpleNamespace
from common import *
import exact
import ctxcodec as cc
from evalctx import train
def ev(i,sid,props,ts=1790000000000,seq=1,**kw):
    d=dict(event_id=str(uuid.uuid4()),session_id=sid,name=kw.get('name','e'),ts=ts,session_elapsed_ms=kw.get('el',0),app_version='1',build_number='b',
           platform='android',os_version='x',device_class='d',locale='ru-RU',timezone_offset_minutes=kw.get('tz',180),properties=props,sequence=seq)
    return d
def check(snap,inst,batches,stateful):
    em=snap.clone();dm=snap.clone()
    for b in batches:
        m=em if stateful else snap.clone();d=dm if stateful else snap.clone()
        f,_=cc.encode(m,inst.install_id,b,stateful);iid,out=cc.decode(d,f,stateful)
        assert iid==inst.install_id and exact.render(inst,out)==exact.render(inst,b),b
        for a,c in zip(b,out):  # also exact Python values incl. -0.0 and types
            for k in a['properties']:
                x,y=a['properties'][k],c['properties'][k]
                assert type(x)==type(y) and (struct.pack('<d',x)==struct.pack('<d',y) if isinstance(x,float) else x==y),(k,x,y)
snap=train('base',100)
inst=SimpleNamespace(install_id=str(uuid.uuid4()))
S='00000000-0000-4000-8000-000000000000'
edge=[ev(0,S,{'neg0':-0.0,'f32':struct.unpack('<f',struct.pack('<f',0.1))[0],'f64':0.1,'big':2**64-1,'min':-(2**63),'max':2**63-1,'none':None,'t':True,'f':False,
              'uni':'遊戲é🙂\u0000"\\/','lone':'\ud800x','empty':'','dec':Decimal('120.00'),'hex':'ab'*40,'HEX':'AB'*8,'uuidU':S.upper(),'dbl_max':1.7976931348623157e308,'tiny':5e-324}),
      ev(1,S,{'neg0':0.0,'big':0,'min':2**63-1,'uni':'遊戲é🙂\u0000"\\/x','dec':Decimal('-0.000')},ts=1790000000000-5,seq=7,tz=-60,el=-1),
      ev(2,str(uuid.uuid4()),{},ts=0,seq=8,name='session_start')]
for sf in (False,True):check(snap,inst,[edge,edge[1:],edge[:1]],sf)
print('edge cases ok')
rng=random.Random(5)
def rv():
    t=rng.randrange(9)
    if t==0:return rng.randrange(-2**63,2**64)
    if t==1:return rng.choice([True,False,None])
    if t==2:return struct.unpack('<f',struct.pack('<f',rng.uniform(-1e3,1e3)))[0]
    if t==3:return rng.uniform(-1e300,1e300)
    if t==4:return ''.join(rng.choice('ab遊🙂é09,;') for _ in range(rng.randrange(0,60)))
    if t==5:return str(uuid.UUID(int=rng.getrandbits(128)))
    if t==6:return rng.randbytes(rng.randrange(1,50)).hex()
    if t==7:return rng.randrange(0,5)
    return Decimal(str(rng.randrange(-10**6,10**6)))/100
for trial in range(300):
    sids=[str(uuid.UUID(int=rng.getrandbits(128))) for _ in range(3)];bs=[];t=rng.randrange(0,2**41);seq=rng.randrange(1,2**40)
    for _ in range(rng.randrange(1,4)):
        b=[]
        for i in range(rng.randrange(1,40)):
            t+=rng.randrange(-1000,100000);seq+=rng.randrange(1,4)
            keys=rng.sample(['a','b','c','block_id','placed_state_hash','x','y_z'],rng.randrange(0,7))
            b.append(ev(i,rng.choice(sids),{k:rv() for k in keys},ts=max(0,t),seq=seq,name=rng.choice(['tap','detail_taken','r'+str(rng.randrange(9))]),el=rng.randrange(-5,10**7),tz=rng.choice([0,60,-180])))
        bs.append(b)
    check(snap,inst,bs,trial%2==1)
print('300 fuzz trials ok (stateless+stateful)')
