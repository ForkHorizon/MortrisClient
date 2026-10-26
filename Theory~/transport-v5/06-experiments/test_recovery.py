import tempfile,unittest,copy
from pathlib import Path
from support import make,rebatch
from model import Model
from recovery import Client,Server,MissingBase
class RecoveryTests(unittest.TestCase):
 def test_lost_ack_restart_and_fallback(self):
  prior=Model(14);i,bs=rebatch(make('base',11,1),20)[0];a,b=bs[:2]
  with tempfile.TemporaryDirectory() as td:
   path=str(Path(td)/'server.db');s=Server(prior,path,{i.install_id});c=Client(prior,i.install_id)
   f=c.begin('first',a);ack=s.receive(f);c.timeout('first') # server committed; client did not.
   f=c.begin('retry',a);self.assertEqual(s.receive(f),ack);self.assertTrue(c.ack('retry',ack));self.assertFalse(c.ack('first',ack))
   self.assertEqual(s.db.execute('select count(*) from e').fetchone()[0],len(a))
   f=c.begin('second',b);s.db.close();s=Server(prior,path,{i.install_id}) # state/ACK cache lost, durable rows remain.
   with self.assertRaises(MissingBase):s.receive(f)
   c.timeout('second');fallback=c.begin('fallback',b,True);ack=s.receive(fallback);self.assertTrue(c.ack('fallback',ack))
   self.assertEqual(s.db.execute('select count(*) from e').fetchone()[0],len(a)+len(b));s.db.close()
 def test_corruption_conflict_and_wrong_ack(self):
  p=Model(14);i,bs=rebatch(make('base',12,1),20)[0];a,b=bs[:2]
  with tempfile.TemporaryDirectory() as td:
   s=Server(p,str(Path(td)/'s.db'),{i.install_id});c=Client(p,i.install_id);f=c.begin('A',a);ack=s.receive(f)
   with self.assertRaises(ValueError):c.ack('A',ack[:-1])
   self.assertIsNone(c.state);self.assertTrue(c.ack('A',ack));old=c.state.state_id();f=c.begin('B',b);bad=f[:-1]+bytes([f[-1]^1])
   with self.assertRaises(ValueError):s.receive(bad)
   self.assertEqual(c.state.state_id(),old);self.assertEqual(s.db.execute('select count(*) from e').fetchone()[0],len(a))
   c.timeout('B');changed=copy.deepcopy(a);changed[0]['properties']['new_field']=42
   f=c.begin('conflict',changed,True)
   with self.assertRaises(ValueError):s.receive(f)
   self.assertEqual(s.db.execute('select count(*) from e').fetchone()[0],len(a));s.db.close()
 def test_origin_denied_and_single_inflight(self):
  p=Model(14);i,bs=rebatch(make('base',13,1),20)[0]
  with tempfile.TemporaryDirectory() as td:
   s=Server(p,str(Path(td)/'s.db'),set());c=Client(p,i.install_id);f=c.begin('A',bs[0])
   with self.assertRaises(ValueError):s.receive(f)
   with self.assertRaises(ValueError):c.begin('B',bs[1])
   self.assertEqual(s.db.execute('select count(*) from e').fetchone()[0],0);s.db.close()
if __name__=='__main__':unittest.main()
