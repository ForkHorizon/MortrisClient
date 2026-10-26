"""Independent stress workload. No game interaction grammar; legal ASCII keys.
Rare types, long UTF-8 values, schema drift, clock jumps, correlated checkpoint text.
Unicode keys are a separate out-of-contract stress mode, not part of legal totals.
"""
import random, uuid, copy
from types import SimpleNamespace
from gen import DEVICES

def dataset_alt(seed, installs=6, count=900):
    rng=random.Random(seed); out=[]
    for i in range(installs):
        inst=SimpleNamespace(install_id=str(uuid.UUID(int=rng.getrandbits(128),version=4)))
        dev=DEVICES[i%len(DEVICES)]; ev=[]; t=1790000000000+i*10000000; state=['.']*600
        sess=str(uuid.UUID(int=rng.getrandbits(128),version=4))
        for n in range(count):
            if n%300==0:sess=str(uuid.UUID(int=rng.getrandbits(128),version=4))
            t+=rng.randrange(1,90000)
            name=rng.choice(['tap','screen','snapshot','purchase'] if n<count//2 else ['gesture','screen_v2','snapshot','purchase'])
            if rng.random()<.08:name='rare_'+str(rng.randrange(80))
            for _ in range(4):state[rng.randrange(len(state))]=rng.choice('0123456789')
            p={'phase':n//450,'counter':n, 'measurement':rng.uniform(-1e6,1e6)}
            if name=='snapshot':p['board']=''.join(state)
            elif rng.random()<.45:p['description']=''.join(rng.choice('遊戲日本語éабв🙂abc0123') for _ in range(130))
            else:p['opaque']=rng.randbytes(160).hex()
            if n>count//2:p['release_label']='mise_à_jour_二'
            ev.append(dict(event_id=str(uuid.UUID(int=rng.getrandbits(128),version=4)),session_id=sess,name=name,ts=t,
                           session_elapsed_ms=n*1700,app_version='2.0' if n<count//2 else '3.0',build_number='alt-build',
                           platform=dev[0],os_version=dev[1],device_class=dev[2],locale=dev[3],timezone_offset_minutes=dev[4],
                           properties=p,sequence=n+1))
        sizes=[1,3,7,25,50,100];bs=[];pos=0
        while pos<len(ev):
            k=rng.choice(sizes);bs.append(ev[pos:pos+k]);pos+=k
        out.append((inst,bs))
    return out
