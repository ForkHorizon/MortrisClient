"""Frozen train202, validation303, new holdout909; independent drift808."""
import sys,random,uuid,hashlib
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'transport-v3/06-experiments'))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'transport-v2/04-experiments'))
from gen import dataset,DEVICES
from alternate import dataset_alt

def make(name,seed,n):
    if name=='alt':return dataset_alt(seed,installs=n)
    return dataset(seed,installs=n,rich=name=='rich')
def rebatch(ds,cap,session=False,deadline=None):
    out=[]
    for i,bs in ds:
        ev=[e for b in bs for e in b];batches=[];current=[]
        for e in ev:
            boundary=current and (len(current)>=cap or (session and e['session_id']!=current[-1]['session_id']) or (deadline is not None and e['ts']-current[0]['ts']>=deadline))
            if boundary:batches.append(current);current=[]
            current.append(e)
        if current:batches.append(current)
        out.append((i,batches))
    return out

def drift(seed=808,n=4,count=600):
    rng=random.Random(seed);out=[]
    for j in range(n):
        inst=SimpleNamespace(install_id=str(uuid.UUID(int=rng.getrandbits(128))));ev=[];t=1790000000000;elapsed=0;sid='';left=0;seq=0
        dev=DEVICES[j%len(DEVICES)]
        for ix in range(count):
            if left==0:sid=str(uuid.UUID(int=rng.getrandbits(128)));left=rng.randint(3,35);elapsed=0
            left-=1;dt=rng.choice([-150,12,33,120,45000]);t+=dt;elapsed+=max(1,dt);seq+=rng.choice([1,1,1,2])
            phase=ix//200
            p={'counter':ix,'numeric':rng.choice([120.0,-0.0,0.005,2**64-1]),'flag':rng.choice([True,False]),'label':rng.choice(['daily','ranked','blitz'])}
            if phase:p['release_label']='release_'+str(phase)
            if phase==2:p['counter']=str(ix)
            if ix%19==0:p['opaque']=rng.randbytes(80).hex()
            if ix%13==0:p['note']='遊戲é🙂'+str(rng.randrange(1000))
            ev.append(dict(event_id=str(uuid.UUID(int=rng.getrandbits(128))),session_id=sid,name=rng.choice(['tap','score','quote','sync']),ts=t,session_elapsed_ms=elapsed,app_version='drift'+str(phase),build_number='drift',platform=dev[0],os_version=dev[1],device_class=dev[2],locale=dev[3],timezone_offset_minutes=dev[4],properties=p,sequence=seq))
        out.append((inst,[ev]))
    return rebatch(out,30,session=True,deadline=30000)
