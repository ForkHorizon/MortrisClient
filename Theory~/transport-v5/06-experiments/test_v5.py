import sys,unittest,copy,random,uuid,struct,json,subprocess,os
from pathlib import Path
from decimal import Decimal
from support import make,rebatch,exact,wire,Reader,u
from model import Model,context_hash,context_bytes
from frame_v5 import encode,decode,render
ROOT=Path(__file__).resolve().parent
class Tests(unittest.TestCase):
    def setUp(self):
        self.inst,self.bs=rebatch(make('base',7,1),100)[0];self.b=self.bs[0][:5];self.prior=Model(14)
    def test_exact_values(self):
        e=self.b[0];vals=[-2**63,2**64-1,-0.0,0.0,120.0,sys.float_info.max,5e-324,Decimal('120.00'),Decimal('-0.000'),None,True,'','日本語🙂','\ud800','\x00','AB'*8]
        for v in vals:
            b=[{**e,'properties':{'value':v}}];f,m=encode(self.prior,self.inst.install_id,b);source,d=decode(self.prior,f);self.assertEqual(source,render(self.inst.install_id,b));self.assertEqual(m.snapshot(True),d.snapshot(True))
    def test_exact_source_and_time(self):
        src=render(self.inst.install_id,self.b,9999)
        src=src.replace(b'"events":',b'"events" : ').replace(b'session_start',b'session_\\u0073tart')
        f,m=encode(self.prior,self.inst.install_id,self.b,source=src);source,d=decode(self.prior,f);self.assertEqual(source,src)
        self.assertIn(b'"sent_at_client":',source)
    def test_canonical_and_rollback(self):
        f,m=encode(self.prior,self.inst.install_id,self.b);before=self.prior.snapshot(True)
        for bad in [f[:-4]+b'\x00'+f[-4:],f[:-4]+b'\x00'*64+f[-4:],f[:-1],f[:-1]+bytes([f[-1]^1])]:
            with self.assertRaises(ValueError):decode(self.prior,bad)
            self.assertEqual(self.prior.snapshot(True),before)
    def test_state_and_retries(self):
        f,client1=encode(self.prior,self.inst.install_id,self.b);source,server1=decode(self.prior,f)
        before=client1.snapshot(True);f2,client2=encode(self.prior,self.inst.install_id,self.bs[1][:5],base=client1)
        self.assertEqual(client1.snapshot(True),before)
        source,server2=decode(self.prior,f2,base=server1);self.assertEqual(client2.state_id(),server2.state_id())
        source,retry=decode(self.prior,f2,base=server1);self.assertEqual(retry.state_id(),server2.state_id())
        bad=bytearray(f2);bad[-1]^=1
        with self.assertRaises(ValueError):decode(self.prior,bytes(bad),base=server1)
        self.assertEqual(server1.state_id(),client1.state_id())
        with self.assertRaises(ValueError):decode(self.prior,f2,base=server2)
        with self.assertRaises(ValueError):decode(self.prior,f2)
    def test_stable_hash_subprocess(self):
        script="import model;print(model.context_hash((('tap','value'),'M',17,8)))"
        results=[]
        for seed in ['1','2','random']:
            env={**os.environ,'PYTHONHASHSEED':seed,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT)}
            results.append(subprocess.check_output([sys.executable,'-c',script],env=env,text=True).strip())
        self.assertEqual(len(set(results)),1)
    def test_snapshot(self):
        f,m=encode(self.prior,self.inst.install_id,self.b)
        restored=Model.restore(m.snapshot(True),state=True);self.assertEqual(restored.state_id(),m.state_id())
        restored=Model.restore(self.prior.snapshot());self.assertEqual(restored.snapshot(),self.prior.snapshot())
        with self.assertRaises(ValueError):Model.restore(self.prior.snapshot()+b'x')
    def test_guards(self):
        e=self.b[0]
        for b in [[],[{**e,'properties':{'bad__key':1}}],[{**e,'properties':{'value':'x'*1025}}],[{**e,'properties':{'x':float('inf')}}]]:
            with self.assertRaises((ValueError,OverflowError)):encode(self.prior,self.inst.install_id,b)
        f,m=encode(self.prior,self.inst.install_id,self.b)
        with self.assertRaises(ValueError):decode(self.prior,f,model_id=2)
    def test_random_batches(self):
        rng=random.Random(555);e=self.b[0];count=0
        for _ in range(80):
            b=[]
            for j in range(rng.randrange(1,12)):
                value=rng.choice([rng.randrange(-2**63,2**64),rng.uniform(-1e100,1e100),None,True,'日本語'+str(rng.randrange(1000))])
                b.append({**e,'sequence':j+1,'ts':e['ts']+j*10,'properties':{'value':value}})
            f,m=encode(self.prior,self.inst.install_id,b);self.assertEqual(decode(self.prior,f)[0],render(self.inst.install_id,b));count+=len(b)
        (ROOT/'results/random-roundtrip.json').write_text(json.dumps({'batches':80,'events':count,'seed':555}))
if __name__=='__main__':unittest.main()
