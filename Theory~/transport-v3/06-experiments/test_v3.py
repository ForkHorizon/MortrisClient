import sys,random,json,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'transport-v2/04-experiments'))
import wire
from gen import dataset
from alternate import dataset_alt
from codec import safe_payload,transform,restore
from frame import pack,unpack,read_u
import zstandard as z

def main():
    d=z.ZstdCompressionDict((ROOT/'results/dict64_base.bin').read_bytes());n=0
    for ds in [dataset(303,installs=3),dataset(303,installs=3,rich=True),dataset_alt(303,installs=3)]:
        for i,bs in ds:
            for b in bs:
                kind,raw=safe_payload(i,b);f=pack(kind,raw,d,1);k,r=unpack(f,{1:d});assert (k,r)==(kind,raw)
                if kind==1:
                    _,ev=wire.mtb2_decode(r);assert wire.v1_json(i,ev,True)==wire.v1_json(i,b,True)
                transformed=transform(b,'replay_hash')
                _,ev=wire.mtb2_decode(wire.mtb2_encode(i,transformed))
                restored=restore(ev,'replay_hash')
                assert wire.v1_json(i,restored,True)==wire.v1_json(i,b,True)
                n+=len(b)
    i,bs=dataset(1,installs=1)[0];e=copy.deepcopy(bs[0][0])
    for val in [1.7976931348623157e308,-0.0,1.2345678901234567,2**64-1,'\x00','日本語']:
        b=[{**e,'properties':{'value':val}}];kind,raw=safe_payload(i,b);assert unpack(pack(kind,raw,d,1),{1:d})==(kind,raw)
    # Type-mismatched context gets safe non-alias form.
    b=[{**e,'properties':{'timezone_offset_minutes':120.0}}];kind,raw=safe_payload(i,b);assert kind==1
    _,decoded=wire.mtb2_decode(raw);assert type(decoded[0]['properties']['timezone_offset_minutes']) is float
    for raw in [b'\xff'*9+b'\x7f',b'\x80\x00']:
        try:read_u(raw,0);raise AssertionError('invalid varint accepted')
        except ValueError:pass
    # Truncation, bomb (declared raw length), trailing bytes, unknown dictionary.
    f=pack(0,b'x'*10000,d,1)
    bad=[f[:-1],f+b'garbage',bytes([0x32,0,99])+f[3:],bytes([0x32,0,1,1])+f[5:]]
    for raw in bad:
        try:unpack(raw,{1:d});raise AssertionError('invalid frame accepted')
        except ValueError:pass
    rng=random.Random(404);rejected=accepted=0
    for _ in range(2000):
        raw=bytearray(f);raw[rng.randrange(len(raw))]^=rng.randrange(1,256)
        try:unpack(bytes(raw),{1:d});accepted+=1
        except ValueError:rejected+=1
    print(json.dumps({'equivalent_events':n,'boundary_cases':9,'malformed_checks':len(bad),'mutations_rejected':rejected,'mutations_decoded':accepted,'note':'TLS supplies integrity; decodable mutations need not be rejected. Payload parser fuzz still required.'},indent=2))
if __name__=='__main__':main()
