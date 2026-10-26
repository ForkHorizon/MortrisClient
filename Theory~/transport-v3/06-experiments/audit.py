"""Adversarial checks of unchanged V2. Run from this directory."""
import sys, json, copy, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'transport-v2/04-experiments'))
import wire
from gen import dataset

def main():
    inst, bs = dataset(1, installs=1)[0]
    e = copy.deepcopy(bs[0][0])
    tests = {'nul': '\x00', 'surrogate': '\ud800', 'negative_zero': -0.0,
             'double17': 1.2345678901234567, 'double_max': 1.7976931348623157e308,
             'i64_min': -2**63, 'u64_max': 2**64-1, 'too_large': 2**64,
             'too_negative': -2**63-1, 'unicode': '日本語😀/\n'}
    out = {}
    for k,v in tests.items():
        b = [{**e, 'properties': {k: v}}]
        try:
            raw = wire.mtb2_encode(inst,b)
            _, d = wire.mtb2_decode(raw)
            out[k] = {'ok': wire.v1_json(inst,b,True)==wire.v1_json(inst,d,True), 'value':repr(d[0]['properties'][k])}
        except Exception as ex:
            out[k] = {'error': type(ex).__name__, 'message':str(ex)}
    for size in (64,65):
        b = [{**e, 'properties': {'a'*size: 1}}]
        try:
            _,d=wire.mtb2_decode(wire.mtb2_encode(inst,b))
            out[f'key_{size}']={'accepted':True,'equivalent':wire.v1_json(inst,b,True)==wire.v1_json(inst,d,True)}
        except Exception as ex: out[f'key_{size}']={'error':type(ex).__name__}
    for name,b in [('empty',[]),('order',[{**e,'properties':{'z':3,'a':1}},{**e,'sequence':e['sequence']+1,'properties':{'a':1,'z':3}}]),
                   ('typed_alias',[{**e,'properties':{'timezone_offset_minutes':float(e['timezone_offset_minutes'])}}]),
                   ('duplicate_seq',[e,e])]:
        try:
            _,d=wire.mtb2_decode(wire.mtb2_encode(inst,b))
            out[name]={'ok':wire.v1_json(inst,b,True)==wire.v1_json(inst,d,True)}
        except Exception as ex: out[name]={'error':type(ex).__name__, 'message':str(ex)}
    out['duplicate_keys']={'input':'{"a":1,"a":2}', 'after_json_parse':json.loads('{"a":1,"a":2}'), 'note':'IReadOnlyDictionary input cannot contain duplicates; raw parser must reject them'}
    value,pos=wire.read_uvarint(b'\xff'*9+b'\x7f',0)
    out['varint_overflow']={'value':value,'bits':value.bit_length(),'accepted':True}
    roots=Path(__file__).resolve().parents[2] / 'transport-v2'
    out['v2_sha256']={str(p.relative_to(roots)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(roots.rglob('*')) if p.is_file() and '__pycache__' not in str(p) and '.venv' not in str(p)}
    print(json.dumps(out,ensure_ascii=True,indent=2))
if __name__=='__main__':main()
