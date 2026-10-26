import copy,random,unittest,uuid
from decimal import Decimal
from support7 import Reader,v6,core,make,rebatch,canonical_source
import string7,metadata7

class Tests(unittest.TestCase):
    def test_exact_strings(self):
        for values in (['']*100,['1,2,4,8','1,2,3,4,8','1,3,4,8','1,3,4,8'],['é🙂abc','é🙂xyzabc','é🙂abc'],['\ud800x','\ud800xy'],['p'*1000+str(i)for i in range(20)]):
            r=Reader(string7.encode(core.T_STR,values));self.assertEqual(string7.decode(r,core.T_STR,len(values)),values);r.end()
        values=[Decimal('1.2300'),Decimal('-0.000'),Decimal('1.2300')]
        r=Reader(string7.encode(core.T_NUMTEXT,values));got=string7.decode(r,core.T_NUMTEXT,3);self.assertEqual(list(map(str,got)),list(map(str,values)));r.end()

    def test_metadata_modes_and_overflow(self):
        rng=random.Random(2801)
        for values in ([metadata7.MIN,metadata7.MAX,0],list(range(500)),[0,1]*250,[1790000000000+sum([10]*(i//4))for i in range(500)],[rng.randint(-10000,10000)for _ in range(500)]):
            r=Reader(metadata7.encode(values));self.assertEqual(metadata7.decode(r,len(values)),values);r.end()
        for raw in (b'',b'\xff',b'\x04\x00',b'\x05\x02'+v6.integers([metadata7.MAX,1])+v6.integers([0,1])):
            with self.assertRaises(ValueError):metadata7.decode(Reader(raw),2)

    def test_invalid_string_refs(self):
        for raw in (b'\xff',b'\x01\x00',b'\x04\x00',b'\x04\x01\xff',b'\x01\x01'+v6.integers([1])+v6.integers([0])+b'\x00'+v6.integers([0])):
            with self.assertRaises(ValueError):string7.decode(Reader(raw),core.T_STR,1)

    def test_logical_strings_binary_modes(self):
        from transport7 import Catalog,Aliases,encode,decode
        rng=random.Random(2802);ids=[str(uuid.UUID(int=rng.getrandbits(128)))for i in range(40)]
        for mode,values in ((2,ids),(3,[f'{rng.getrandbits(128):032x}'for _ in range(40)]),(4,['']+ids)):
            raw=string7.encode(core.T_STR,values);self.assertEqual(raw[0],mode)
            r=Reader(raw);self.assertEqual(string7.decode(r,core.T_STR,len(values)),values);r.end()
        ds=rebatch(make('base',2801,1),100);i,bs=ds[0];b=copy.deepcopy(bs[0])
        for e in b:e['properties']={'value':''}
        c=Catalog.train('logical_strings',[(i,[b])],logical_strings=True)
        self.assertEqual(Catalog.load(c.data).data,c.data)
        for e,value in zip(b,ids+['ABCDEF','a b c d','é','\ud800']):e['properties']['value']=value
        self.assertTrue(all(c.shape(e)in c.ids for e in b))
        a=Aliases(bytes(8));a.register(i.install_id,b)
        f=encode(c,a,i.install_id,b,string_model=True,integer_model=True)
        o,got=decode(c,a,f,authorized_project=c.project,authorized_origin=i.install_id)
        self.assertEqual(canonical_source(o,got,True),canonical_source(o,b,True))

    def test_full_frames_all_combinations(self):
        from transport7 import Catalog,Aliases,encode,decode
        ds=rebatch(make('base',2801,1),100);i,bs=ds[0];b=bs[0];c=Catalog.train('tables_project',ds);a=Aliases(bytes(8));a.register(i.install_id,b)
        for sm in (False,True):
            for mm in (False,True):
                for full in (False,True):
                    f=encode(c,a,i.install_id,b,preserve_ids=full,integer_model=True,string_model=sm,metadata_model=mm)
                    o,ev=decode(c,a,f,authorized_project=c.project,authorized_origin=i.install_id)
                    self.assertEqual(canonical_source(o,ev,full),canonical_source(o,b,full))
if __name__=='__main__':unittest.main()
