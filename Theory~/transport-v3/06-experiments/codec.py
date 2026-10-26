"""V3 experiments. No product code. Safe V2 subset + exact raw-JSON escape.
Predictive transformation is reversible and verifies every transformed field.
"""
import copy, math, struct, json, hashlib
from decimal import Decimal
import wire
# V2 reference remains unchanged. Guard its unsafe float32 probe in this process.
def safe_f32(x):
    try:return struct.unpack('<f',struct.pack('<f',x))[0]==x
    except OverflowError:return False
wire._is_f32=safe_f32

def transform(batch,mode):
    out=copy.deepcopy(batch); prev={};prev2={}; hashprev=None
    for e in out:
        for k,v in list(e['properties'].items()):
            key=(e['name'],k) if mode=='per_type' else k
            last=prev.get(key); last2=prev2.get(key)
            if mode in ('linear','per_type') and type(v) is int:
                prediction=last if last is not None else 0
                if mode=='linear' and last2 is not None:prediction=2*last-last2
                residual=v-prediction
                e['properties'][k]=residual
                assert residual+prediction==v
            elif mode=='xor' and type(v) is float:
                val=int.from_bytes(struct.pack('<d',v),'little');p=last if last is not None else 0
                e['properties'][k]=val^p
                assert struct.pack('<d',v)==(e['properties'][k]^p).to_bytes(8,'little')
                v=val
            elif mode=='prefix' and type(v) is str:
                p=last if last is not None else ''; n=0
                while n<min(len(v),len(p)) and v[n]==p[n]:n+=1
                e['properties'][k]=str(n)+':'+v[n:]
                assert p[:n]+e['properties'][k].split(':',1)[1]==v
            prev2[key]=last;prev[key]=v
        if mode=='replay_hash' and 'placed_state_hash' in e['properties']:
            current=e['properties']['placed_state_hash'];p=e['properties']
            predicted=hashprev
            if e['name']=='placement_resolved' and p.get('outcome')=='placed' and hashprev is not None:
                predicted=hashlib.sha256(hashprev.encode()+bytes([p['block_id'],p['cell_x'],p['cell_y']])).hexdigest()
            # Escape on first hash / resets / arbitrary game algorithm.
            e['properties']['placed_state_hash']='=' if current==predicted else current
            restored=predicted if e['properties']['placed_state_hash']=='=' else e['properties']['placed_state_hash']
            assert restored==current
            hashprev=current
    return out

def safe_payload(inst,batch):
    # Always verify a restricted optimized candidate; otherwise exact original bytes.
    want=wire.v1_json(inst,batch,True)
    try:
        # CTXREF must preserve serialized type too. Disable aliasing for uncommon
        # numeric context overlap rather than accepting Python's 120 == 120.0.
        alias=not any(k in wire.DEVICE_KEYS and type(v) is not type(e[k]) for e in batch for k,v in e['properties'].items())
        raw=wire.mtb2_encode(inst,batch,aliases=alias)
        _,ev=wire.mtb2_decode(raw)
        if wire.v1_json(inst,ev,True)==want:return 1,raw
    except (ValueError,OverflowError,UnicodeError,AssertionError,IndexError):pass
    return 0,want

def restore(batch,mode):
    if mode!='replay_hash':raise ValueError('only replay_hash decoder is specified')
    out=copy.deepcopy(batch);previous=None
    for e in out:
        p=e['properties']
        if 'placed_state_hash' not in p:continue
        predicted=previous
        if e['name']=='placement_resolved' and p.get('outcome')=='placed' and previous is not None:
            predicted=hashlib.sha256(previous.encode()+bytes([p['block_id'],p['cell_x'],p['cell_y']])).hexdigest()
        if p['placed_state_hash']=='=':
            if predicted is None:raise ValueError('hash reference before anchor')
            p['placed_state_hash']=predicted
        previous=p['placed_state_hash']
    return out
