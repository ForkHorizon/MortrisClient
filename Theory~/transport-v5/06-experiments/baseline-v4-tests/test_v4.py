import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'transport-v4/06-experiments'))
import copy,json,random,struct,sys,unittest,zlib,gzip
from decimal import Decimal
from pathlib import Path
import core,exact,framing,wire,transport
from primitives import Reader,u,ints,readints,floats,readfloats,packbits,readbits
from workloads import make,rebatch,drift
from reliability import Queue,Server
import tempfile
ROOT=Path(__file__).resolve().parent
class Tests(unittest.TestCase):
    def test_vectors(self):
        rng=random.Random(707)
        vectors=[[],[-2**63,2**63-1],[0]*500,list(range(500)),list(range(500,-1,-1)),[-1,0,1]]
        vectors += [[rng.randrange(-100000,100000) for _ in range(rng.randrange(1,500))] for _ in range(100)]
        for vs in vectors:
            for advanced in (False,True):
                b=ints(vs,advanced);r=Reader(b);self.assertEqual(readints(r,len(vs)),vs);r.end()
        for size in (4,8):
            vs=[-0.0,0.0,1.0,120.0,0.005,1.5] if size==4 else [-0.0,0.0,5e-324,sys.float_info.max,1.2345678901234567]
            b=floats(vs,size,True);r=Reader(b);got=readfloats(r,len(vs),size);r.end()
            fmt='<f' if size==4 else '<d';self.assertEqual([struct.pack(fmt,x) for x in got],[struct.pack(fmt,x) for x in vs])
    def test_all_profiles(self):
        count=0
        for ds in [make('base',707,2),make('rich',707,2),make('alt',707,2),drift(707,2,250)]:
            for inst,bs in ds:
                for batch in bs:
                    for replay in (False,True):
                        raw,tail=core.encode(inst,batch,replay=replay);_,ev=core.decode(raw,tail)
                        self.assertEqual(exact.render(inst,ev),exact.render(inst,batch));count+=len(batch)
        (ROOT/'results/roundtrip-count.json').write_text(json.dumps({'events_including_both_modes':count,'seed':707}))
    def test_boundaries(self):
        inst,bs=make('base',1,1)[0];e=bs[0][0]
        vals=[-2**63,2**63-1,2**64-1,-0.0,sys.float_info.max,5e-324,True,1,120.0,Decimal('120.00'),Decimal('-0.00'),'\ud800','\x00','é🙂日本語',None]
        for v in vals:
            b=[{**e,'properties':{'value':v,'timezone_offset_minutes':120.0}}]
            raw,tail=exact.encode(inst,b);source,_,_=exact.decode(raw,tail);self.assertEqual(source,exact.render(inst,b))
        with self.assertRaises(ValueError):core.encode(inst,[])
        b=[{**e,'properties':{'value':0.0}}];base=exact.render(inst,b)
        for source in [base.replace(b'0.0',b'-0.00'),base.replace(b'"events":',b'"events" : '),base.replace(b'session_start',b'session_\\u0073tart')]:
            raw,tail=exact.encode(inst,b,source=source);self.assertEqual(exact.decode(raw,tail)[0],source)
    def test_full_requests(self):
        inst,bs=make('base',7,1)[0];b=bs[0][:20];source=exact.render(inst,b)
        for src in [source,source.replace(b'"events":',b'"events" : '),source.replace(b'session_start',b'session_\\u0073tart')]:
            frame=transport.encode(inst,b,source=src,trailer=True)
            self.assertEqual(transport.decode(frame,{}),src)
        # Formula is a negotiated profile limit, not a universal SDK bound.
        b=[{**b[0],'app_version':'a'*20000}]
        with self.assertRaises(ValueError):transport.encode(inst,b)
        self.assertTrue(exact.render(inst,b)) # Source is retained for the existing V1 path.
    def test_digest(self):
        a=b'{"session_id":"a","name":"tap","properties":{"x":120.00},"sequence":1}'
        b=b'{ "session_id" : "\\u0061", "name":"tap", "properties":{"x":120.00}, "sequence":1,"event_id":"old"}'
        self.assertEqual(exact.digest('p','o',a),exact.digest('p','o',b))
        for c in [a.replace(b'120.00',b'120.0'),a.replace(b'"a"',b'"b"'),a.replace(b'"tap"',b'"click"')]:self.assertNotEqual(exact.digest('p','o',a),exact.digest('p','o',c))
        with self.assertRaises(ValueError):exact.canonical_event(b'{"x":1,"x":2}')
    def test_requests(self):
        q=Queue();q.enqueue(range(1,8));q.send('A',[1,2,3]);q.send('B',[4,5,6]);self.assertEqual(q.ack('B',b'\x40\x01'),[4,5,6]);self.assertEqual(q.pending(),[1,2,3,7])
        q.timeout('A');q.send('retry',[1,2,3]);self.assertEqual(q.ack('A',b'\x40\x01'),[])
        self.assertEqual(q.ack('retry',b'\x41\x01\x01\x01\x01'),[1,3]);self.assertEqual(q.pending(),[2,7])
        q.send('conflict',[2,7]);self.assertEqual(q.ack('conflict',b'\x42\x01'),[]);self.assertEqual(q.pending(),[2,7])
        q.send('malformed',[2,7])
        with self.assertRaises(ValueError):q.ack('malformed',b'\x40\x01X')
        self.assertEqual(q.pending(),[2,7])
    def test_server_retries(self):
        with tempfile.TemporaryDirectory() as td:
            path=str(Path(td)/'server.db');server=Server(path)
            self.assertEqual(server.commit({'o'},'o',[(1,b'a'),(3,b'c')]),[1,3])
            server.db.close();server=Server(path) # Lost ACK and server restart.
            self.assertEqual(server.commit({'o'},'o',[(1,b'a')]),[1])
            self.assertEqual(server.commit({'o'},'o',[(2,b'b'),(3,b'c')]),[2,3])
            with self.assertRaises(ValueError):server.commit({'o'},'o',[(4,b'd'),(3,b'changed')])
            self.assertEqual(server.db.execute('select count(*) from events').fetchone()[0],3)
            with self.assertRaises(ValueError):server.commit({'foreign'},'o',[(4,b'd')])
            server.db.close()
    def test_frames(self):
        for data in [b'x',b'x'*10000,random.Random(3).randbytes(10000)]:
            f=framing.pack(data,b'rawtail',2,level=9,adaptive=True);self.assertEqual(framing.unpack(f,{})[1:3],(data,b'rawtail'))
            for bad in [f[:-1],f+b'garbage']:
                with self.assertRaises(ValueError):framing.unpack(bad,{})
        bombs=[b'\x41\x01\x01\x00'+u(10)+b'\x00'+gzip.compress(b'x'*2000000),b'\x40\x01\x01\x00'+u(2000000)+b'\x00x']
        for b in bombs:
            with self.assertRaises(ValueError):framing.unpack(b,{})
        for b in [b'\xff'*9+b'\x02',b'\x80\x00']:
            with self.assertRaises(ValueError):Reader(b).u()
    def test_fuzz(self):
        inst,bs=make('base',2,1)[0];raw,tail=core.encode(inst,bs[0]);frame=framing.pack(raw,tail,len(bs[0]));rng=random.Random(505);counts={'outer_rejected':0,'core_rejected':0,'decoded':0}
        for _ in range(3000):
            f=bytearray(frame);f[rng.randrange(len(f))]^=rng.randrange(1,256)
            try:_,r,t,n=framing.unpack(bytes(f),{})
            except ValueError:counts['outer_rejected']+=1;continue
            try:
                _,ev=core.decode(r,t)
                if len(ev)!=n:raise ValueError('count mismatch')
            except (ValueError,UnicodeError,OverflowError,struct.error):counts['core_rejected']+=1;continue
            counts['decoded']+=1
        # Direct parser mutation bypasses compressor rejection.
        counts['payload_rejected']=counts['payload_decoded']=0
        for _ in range(3000):
            f=bytearray(raw);f[rng.randrange(len(f))]^=rng.randrange(1,256)
            try:core.decode(bytes(f),tail)
            except (ValueError,UnicodeError,OverflowError,struct.error):counts['payload_rejected']+=1;continue
            counts['payload_decoded']+=1
        (ROOT/'results/fuzz.json').write_text(json.dumps(counts,indent=2))
if __name__=='__main__':unittest.main()
