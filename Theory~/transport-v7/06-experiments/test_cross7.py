import copy,random,unittest
from support7 import Reader,v6,make,rebatch
import cross7,numeric7

class Tests(unittest.TestCase):
    def test_reference_modes_missing_and_window(self):
        rng=random.Random(2901);rows=list(range(100))
        owners=[dict(ts=1790000000000+i*17,sequence=i+1,session_elapsed_ms=i*13)for i in rows]
        sources=[{i:rng.randint(-10**12,10**12)for i in rows}for _ in range(16)]
        sources[0].pop(0)
        for mode,values in ((5,[sources[0].get(i,0)for i in rows]),(6,[-sources[0].get(i,0)for i in rows])):
            raw=cross7.encode(values,owners,rows,sources)
            self.assertEqual(raw[:2],bytes([mode,16]));r=Reader(raw)
            self.assertEqual(cross7.decode(r,100,owners,rows,sources),values);r.end()

    def test_malformed_and_overflow(self):
        owners=[dict(ts=0,sequence=1,session_elapsed_ms=0)];previous=[{0:numeric7.MAX}]
        for raw in (b'',b'\xff',b'\x05\x00',b'\x05\x11',b'\x05\x02',b'\x05\x01'+v6.integers([1])):
            with self.assertRaises(ValueError):cross7.decode(Reader(raw),1,owners,[0],previous)
        for value in (numeric7.MIN,numeric7.MAX):
            raw=cross7.encode([value],owners,[0],previous);r=Reader(raw)
            self.assertEqual(cross7.decode(r,1,owners,[0],previous),[value]);r.end()

    def test_full_raw_rewrite(self):
        from transport7 import Catalog,Aliases,raw_encode
        ds=rebatch(make('base',2901,1),100);inst,bs=ds[0];batch=copy.deepcopy(bs[0]);rng=random.Random(2902)
        for i,e in enumerate(batch):
            basis=rng.randrange(-10**8,10**8)
            e['properties']={'first':basis,'second':-basis,'text':'project-neutral-'+str(i),'flag':bool(i%2),'maybe':None}
            if i%3:e['properties']['extra']=basis+12
        for logical in (False,True):
            c=Catalog.train('cross_project',[(inst,[batch])],logical_strings=logical);a=Aliases(bytes(8));a.register(inst.install_id,batch)
            for ids in (False,True):
                base=raw_encode(c,a,inst.install_id,batch,ids,True,True)
                packed,modes=cross7.rewrite(base,c,batch,ids)
                restored,_=cross7.rewrite(packed,c,batch,ids,True)
                self.assertEqual(restored,base);self.assertTrue(set(modes)&{5,6})
if __name__=='__main__':unittest.main()
