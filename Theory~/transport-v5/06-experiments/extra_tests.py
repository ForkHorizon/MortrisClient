import unittest,hashlib
from pathlib import Path
from model import load_artifact,Model
from support import make,rebatch
from frame_v5 import encode,decode,render
ROOT=Path(__file__).resolve().parent
class ExtraTests(unittest.TestCase):
 def test_asset_identity_and_limits(self):
  b=(ROOT/'results/prior14-base.zlib').read_bytes();m=load_artifact(b,hashlib.sha256(b).hexdigest());self.assertEqual(m.bits,14)
  with self.assertRaises(ValueError):load_artifact(b,'0'*64)
  with self.assertRaises(ValueError):load_artifact(b+b'junk',hashlib.sha256(b+b'junk').hexdigest())
 def test_deadline_leaves_prior(self):
  p=Model(14);i,bs=rebatch(make('base',9,1),100)[0];f,m=encode(p,i.install_id,bs[0][:5]);old=p.snapshot()
  with self.assertRaises(ValueError):decode(p,f,timeout_seconds=-1)
  self.assertEqual(p.snapshot(),old)
 def test_source_boundary(self):
  p=Model(14);i,bs=rebatch(make('base',9,1),100)[0];b=bs[0][:2];src=render(i.install_id,b)
  cases=[src.replace(b'"sequence":1',b'"sequence":99',1),src.replace(b'"properties":{',b'"properties":{"bad__key":1,',1)]
  for bad in cases:
   with self.assertRaises(ValueError):encode(p,i.install_id,b,source=bad)
 def test_rule_is_exact_not_assumed(self):
  p=Model(14);i,bs=rebatch(make('base',10,1),100)[0]
  for batch in [bs[0][:20],[{**bs[0][0],'properties':{'placed_state_hash':'日本語'}},{**bs[0][1],'properties':{'outcome':'placed','block_id':1,'cell_x':1,'cell_y':2,'placed_state_hash':'nothex'}}]]:
   f,m=encode(p,i.install_id,batch,hash_rule=True);self.assertEqual(decode(p,f)[0],render(i.install_id,batch))
if __name__=='__main__':unittest.main()
