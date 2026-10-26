import random,unittest
from numeric7 import *

class Tests(unittest.TestCase):
    def test_all_candidates_and_edges(self):
        rng=random.Random(2701)
        fixtures=[[MIN,MAX,0], [0]*100,list(range(100)),[i%3 for i in range(100)], [rng.randrange(-10000,10000)for _ in range(500)]]
        for values in fixtures:
            owners=[{'ts':1790000000000+i*123,'sequence':i+1,'session_elapsed_ms':i*123}for i in range(len(values))]
            for mode,payload in options(values,owners).items():
                r=Reader(bytes([mode])+payload);self.assertEqual(decode(r,len(values),owners),values);r.end()
            r=Reader(encode(values,owners));self.assertEqual(decode(r,len(values),owners),values);r.end()

    def test_invalid_modes_indices_and_overflow(self):
        owners=[{'ts':MAX,'sequence':1,'session_elapsed_ms':0}]
        for raw in (b'\xff',b'\x04\x00',b'\x04\x01'+v6.integers([0])+v6.integers([1]),b'\x01'+v6.integers([1])):
            with self.assertRaises(ValueError):decode(Reader(raw),1,owners)

    def test_frame_roundtrip_flags(self):
        from support7 import make,rebatch,canonical_source
        from transport7 import Catalog,Aliases,encode as frame_encode,decode as frame_decode
        ds=rebatch(make('base',2701,1),100);inst,bs=ds[0];b=bs[0];c=Catalog.train('numeric_project',ds)
        a=Aliases(bytes(8));a.register(inst.install_id,b)
        for full in (False,True):
            f=frame_encode(c,a,inst.install_id,b,preserve_ids=full,integer_model=True)
            o,ev=frame_decode(c,a,f,authorized_project=c.project,authorized_origin=inst.install_id)
            self.assertEqual(canonical_source(o,ev,full),canonical_source(o,b,full))
if __name__=='__main__':unittest.main()
