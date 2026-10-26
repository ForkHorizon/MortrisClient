from support7 import canonical_source
import copy, hashlib, unittest, zlib, struct
from support7 import v6, make, rebatch, z
from transport7 import *
from game_cleanup import clean_properties

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ds = rebatch(make('base',202,2),100)
        cls.c = Catalog.train('project_a',cls.ds)
        cls.inst,bs=cls.ds[0];cls.b=bs[0]
        cls.a=Aliases(bytes(8));cls.server=Aliases(bytes(8));cls.server.accept(cls.a.register(cls.inst.install_id,[e for b in bs for e in b]))
        raw=[raw_encode(cls.c,cls.a,cls.inst.install_id,b,False) for b in bs]
        cls.d=z.train_dictionary(1024,raw * 5,level=1)

    def test_roundtrip_full_and_legacy(self):
        for full in (True,False):
            for d in (None,self.d):
                f=encode(self.c,self.a,self.inst.install_id,self.b,d,full)
                o,ev=decode(self.c,self.server,f,d,authorized_project='project_a',authorized_origin=self.inst.install_id)
                self.assertEqual(canonical_source(o,ev,full),canonical_source(o,self.b,full))

    def test_cross_project_catalog_epoch_and_dictionary(self):
        f=encode(self.c,self.a,self.inst.install_id,self.b,self.d)
        self.assertNotEqual(self.c.id,Catalog('project_b',self.c.shapes).id)
        for c,a,d,p,o in [(self.c,self.server,None,'project_a',self.inst.install_id),
                          (self.c,Aliases(b'12345678'),self.d,'project_a',self.inst.install_id),
                          (self.c,self.server,self.d,'project_b',self.inst.install_id),
                          (self.c,self.server,self.d,'project_a','0'*36)]:
            with self.assertRaises((ValueError,z.ZstdError)):decode(c,a,f,d,authorized_project=p,authorized_origin=o)
        self.assertEqual(Catalog.load(self.c.data).data,self.c.data)

    def test_corruption_truncation_and_unknown_schema(self):
        f=encode(self.c,self.a,self.inst.install_id,self.b,self.d)
        for ix in range(len(f)):
            altered=bytearray(f);altered[ix]^=1
            with self.assertRaises((ValueError,z.ZstdError)):decode(self.c,self.server,bytes(altered),self.d,authorized_project='project_a',authorized_origin=self.inst.install_id)
        for end in (0,1,28,len(f)-1):
            with self.assertRaises(ValueError):decode(self.c,self.server,f[:end],self.d,authorized_project='project_a',authorized_origin=self.inst.install_id)
        unknown=copy.deepcopy(self.b);unknown[0]['properties']['new_property']=12
        with self.assertRaises(KeyError):encode(self.c,self.a,self.inst.install_id,unknown)

    def test_property_order_is_not_a_schema_change(self):
        b=copy.deepcopy(self.b)
        for e in b:e['properties']=dict(reversed(list(e['properties'].items())))
        f=encode(self.c,self.a,self.inst.install_id,b,self.d)
        o,ev=decode(self.c,self.server,f,self.d,authorized_project='project_a',authorized_origin=self.inst.install_id)
        self.assertEqual(canonical_source(o,ev,True),canonical_source(o,b,True))
        self.assertEqual(Catalog.train('project_a',[(self.inst,[b])]).shapes,sorted({shape(e)for e in b}))

    def test_valid_crc_rejections(self):
        f=encode(self.c,self.a,self.inst.install_id,self.b,self.d)
        for ix in (0,2,3,4,12,20,28):
            altered=bytearray(f[:-4]);altered[ix]^=128
            altered+=struct.pack('<I',zlib.crc32(altered))
            with self.assertRaises((ValueError,z.ZstdError)):
                decode(self.c,self.server,bytes(altered),self.d,authorized_project='project_a',authorized_origin=self.inst.install_id)

    def test_invalid_typed_boundary(self):
        b=copy.deepcopy(self.b[:1]);b[0]['properties']={'text':'a'*1025}
        c=Catalog.train('boundary',[(self.inst,[b])]);f=encode(c,self.a,self.inst.install_id,b)
        with self.assertRaises(ValueError):decode(c,self.server,f,authorized_project='boundary',authorized_origin=self.inst.install_id)

    def test_safe_cleanup(self):
        p={'attempt_id':'a','wave_attempt_id':'a','placed_block_ids':'','placed_state_hash':hashlib.sha256(b'').hexdigest(),'interaction_id':'id','interaction_index':1}
        out=clean_properties(p,migrate_interactions=True)
        self.assertEqual(out,{'attempt_id':'a','placed_block_ids':'','interaction_index':1})
        for patch in ({'placed_state_hash':'bad'},{'placed_block_ids_truncated':True}):
            self.assertIn('placed_state_hash',clean_properties(dict(p,**patch)))
        self.assertIn('placed_state_hash',clean_properties({'placed_state_hash':p['placed_state_hash']}))
        self.assertIn('wave_attempt_id',clean_properties(dict(p,wave_attempt_id='different')))
        self.assertIn('interaction_id',clean_properties(dict(p,interaction_index=0),migrate_interactions=True))
        self.assertIn('interaction_id',clean_properties(p))

    def test_typed_edges(self):
        from decimal import Decimal
        b=copy.deepcopy(self.b[:3])
        for i,e in enumerate(b):
            e['properties']={'flag':bool(i%2),'nothing':None,'negative':-(1<<63)+i,'large':(1<<64)-1,'float':[-0.0,1.25,0.005][i],'text':'遊戲é🙂','decimal':Decimal('1.2300'),'hex':'abcdef','uid':e['event_id']}
        c=Catalog.train('edge',[(self.inst,[b])]);f=encode(c,self.a,self.inst.install_id,b)
        o,ev=decode(c,self.server,f,authorized_project='edge',authorized_origin=self.inst.install_id)
        self.assertEqual(canonical_source(o,ev,True),canonical_source(o,b,True))
        self.assertEqual(struct.pack('<d',ev[0]['properties']['float']),struct.pack('<d',-0.0))

if __name__=='__main__':unittest.main()
