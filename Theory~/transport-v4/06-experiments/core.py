"""MTB4 research core, adapted from V2 with independent bounded decoder.
Only experiments; source V2/V3 and product remain unchanged.
"""
import sys,copy,hashlib,uuid as uuidlib,struct,math,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'transport-v2/04-experiments'))
import wire
from wire import UUID_RE,HEX_RE,jdump,PROJECT_ID,sent_at
from primitives import u as uvarint,zz,ints,readints,packbits,readbits,floats,readfloats,Reader
from decimal import Decimal
DEVICE_KEYS=wire.DEVICE_KEYS

def _is_f32(x):
    try:return struct.unpack('<f',struct.pack('<f',x))[0]==x
    except OverflowError:return False
wire._is_f32=_is_f32
T_PRED=12
class Pred:pass
PRED=Pred()
def _vtype(v):
    if v is PRED:return T_PRED
    return _vtype_base(v)
def hash_prediction(previous,e):
    if previous is None:return None
    p=e['properties']
    if e['name']=='placement_resolved' and p.get('outcome')=='placed':
        xyz=[p.get(k) for k in ('block_id','cell_x','cell_y')]
        if any(type(v) is not int or not 0<=v<=255 for v in xyz):return None
        return hashlib.sha256(previous.encode('ascii')+bytes(xyz)).hexdigest()
    return previous
def mark_hashes(batch):
    previous=None
    for e in batch:
        p=e['properties'];v=p.get('placed_state_hash')
        if type(v) is not str or len(v)!=64 or not HEX_RE.fullmatch(v):continue
        prediction=hash_prediction(previous,e)
        p['placed_state_hash']=PRED if v==prediction else v
        previous=v
    # One type for anchors and predictions, no STR/HEX split.
T_INT, T_STR, T_BOOL, T_F32, T_F64, T_UUID, T_HEX, T_NULL, T_ALIAS, T_CTXREF, T_U64, T_NUMTEXT = range(12)
SDK_NAME, SDK_VERSION = "mortris-unity", "0.2.0"
CTX_FIELDS = DEVICE_KEYS  # ctx table field order after session uuid


def _vtype_base(v):
    if v is None:
        return T_NULL
    if isinstance(v, bool):
        return T_BOOL
    if isinstance(v, int):
        
        if not -(1<<63)<=v<1<<64:raise ValueError("integer domain")
        return T_INT if v < 2 ** 63 else T_U64
    if isinstance(v, float):
        return T_F32 if _is_f32(v) else T_F64  # a real SDK tags float vs double from the CLR type
    if isinstance(v, Decimal):
        return T_NUMTEXT
    if UUID_RE.match(v):
        return T_UUID
    if HEX_RE.match(v):
        return T_HEX
    return T_STR


class _Tab:
    def __init__(self):
        self.items, self.idx = [], {}

    def id(self, v):
        if v not in self.idx:
            self.idx[v] = len(self.items)
            self.items.append(v)
        return self.idx[v]


def encode(inst, batch, advanced=True, ef=True, float_opt=True, local=True, split_strings=True, trailer=False, replay=False, sections=None):
    aliases=True;with_install=True
    if not 1<=len(batch)<=500:raise ValueError("event count")
    batch=copy.deepcopy(batch) if replay else batch
    if replay:mark_hashes(batch)
    """Returns payload bytes (before compression).
    columnar=False writes the identical tokens row-major (isolates layout effect; not decodable here).
    known: set of 8-byte fingerprints the server already holds (content-addressed ctx/shape cache, spec 5.6).
    sections: optional dict to receive per-section byte counts."""
    strs, uuids, hexes = _Tab(), _Tab(), _Tab()
    ctx_tab, shape_tab = _Tab(), _Tab()
    # ---- pass 1: shapes and contexts
    ev_shape, ev_ctx = [], []
    for e in batch:
        c = (e["session_id"],) + tuple(e[k] for k in CTX_FIELDS)
        ev_ctx.append(ctx_tab.id(c))
        ctxd = dict(zip(CTX_FIELDS, c[1:]))
        fields = []
        keys = list(e["properties"])
        for k, v in e["properties"].items():
            t = T_PRED if replay and k=="placed_state_hash" and (v is PRED or (type(v) is str and len(v)==64 and HEX_RE.fullmatch(v))) else _vtype(v)
            if aliases and k in ctxd and type(ctxd[k]) is type(v) and jdump(ctxd[k]) == jdump(v):
                t = T_CTXREF
            fields.append((k, t))
        ev_shape.append((e["name"], tuple(fields), keys))
    # alias detection: per (name, fields) keep T_ALIAS(j) only if it holds for every event of that shape in batch
    shape_alias = {}
    if aliases:
        for (name, fields, keys), e in zip(ev_shape, batch):
            sk = (name, fields)
            p = e["properties"]
            cand = {i: {j for j in range(i) if fields[j][1] == fields[i][1] and jdump(p[keys[j]]) == jdump(p[keys[i]])}
                    for i in range(len(fields)) if fields[i][1] in (T_UUID, T_STR, T_HEX, T_INT)}
            if sk not in shape_alias:
                shape_alias[sk] = cand
            else:
                shape_alias[sk] = {i: shape_alias[sk][i] & cand.get(i, set()) for i in shape_alias[sk]}
    ev_shape_id = []
    for name, fields, _ in ev_shape:
        al = shape_alias.get((name, fields), {})
        f2 = tuple((k, (T_ALIAS, min(al[i])) if al.get(i) else t) for i, (k, t) in enumerate(fields))
        ev_shape_id.append(shape_tab.id((name, f2)))
    # ---- columns
    cols, col_order = {}, []

    def col(key):
        if key not in cols:
            cols[key] = []
            col_order.append(key)
        return cols[key]

    shape_col, ctx_col, dt_col, el_col = [], [], [], []
    prev_ts, prev_el = batch[0]["ts"], {}
    for e, sid, cid in zip(batch, ev_shape_id, ev_ctx):
        shape_col.append(sid)
        ctx_col.append(cid)
        dt_col.append(e["ts"] - prev_ts)
        prev_ts = e["ts"]
        pe = prev_el.get(cid)
        el_col.append(e["session_elapsed_ms"] if pe is None else e["session_elapsed_ms"] - (pe[0] + e["ts"] - pe[1]))
        prev_el[cid] = (e["session_elapsed_ms"], e["ts"])
        name, fields = shape_tab.items[sid]
        for (k, t), v in zip(fields, e["properties"].values()):
            if isinstance(t, tuple) or t in (T_CTXREF, T_NULL):
                continue
            col((k, t)).append(v)

    def enc_col(t, vals):
        if t==T_INT:return b"",[ints(vals,advanced,ef)]
        if t in (T_F32,T_F64):return b"",[floats(vals,4 if t==T_F32 else 8,float_opt)]
        if t==T_BOOL:return b"",[packbits([int(v) for v in vals],1)]
        if t==T_U64:return b"",[uvarint(v) for v in vals]
        if t==T_PRED:
            bits=[int(v is PRED) for v in vals]
            return b"",[packbits(bits,1)+b"".join(bytes.fromhex(v) for v in vals if v is not PRED)]
        table={T_STR:strs,T_NUMTEXT:strs,T_UUID:uuids,T_HEX:hexes}.get(t)
        if table is None:raise ValueError(t)
        ids=[table.id(str(v) if t==T_NUMTEXT else v) for v in vals]
        direct=b"\x00"+ints(ids,advanced,ef)
        if local:
            unique=list(dict.fromkeys(ids));lookup={v:i for i,v in enumerate(unique)}
            alt=b"\x01"+uvarint(len(unique))+b"".join(uvarint(v) for v in unique)+ints([lookup[v] for v in ids],advanced,ef)
            direct=min((direct,alt),key=len)
        return b"",[direct]

    enc = [(k, t, *enc_col(t, cols[(k, t)])) for (k, t) in col_order]
    # ---- serialize tables (strings referenced by index into strs)
    ctx_bytes = bytearray(uvarint(len(ctx_tab.items)))
    for c in ctx_tab.items:
        body = uuidlib.UUID(c[0]).bytes + b"".join(uvarint(strs.id(v)) for v in c[1:-1]) + uvarint(zz(c[-1]))
        ctx_bytes += body
    shape_bytes = bytearray(uvarint(len(shape_tab.items)))
    for name, fields in shape_tab.items:
        sb = uvarint(strs.id(name)) + uvarint(len(fields))
        for k, t in fields:
            sb += uvarint(strs.id(k))
            sb += bytes([T_ALIAS]) + uvarint(t[1]) if isinstance(t, tuple) else bytes([t])
        shape_bytes += sb
    head = bytes([4]) + uvarint(1 if with_install else 0) + (uuidlib.UUID(inst.install_id).bytes if with_install else b"")
    seqs = [e["sequence"] for e in batch]
    gaps = [(i, seqs[i] - seqs[i - 1] - 1) for i in range(1, len(seqs)) if seqs[i] != seqs[i - 1] + 1]
    head += uvarint(seqs[0]) + uvarint(len(batch)) + uvarint(len(gaps)) + b"".join(uvarint(i) + uvarint(g) for i, g in gaps)
    head += uvarint(batch[0]["ts"]) + uvarint(zz(sent_at(batch) - batch[-1]["ts"]))
    meta = uvarint(strs.id(PROJECT_ID)) + uvarint(strs.id(SDK_NAME)) + uvarint(strs.id(SDK_VERSION))
    string_bytes=[s.encode('utf-8',errors='surrogatepass') for s in strs.items]
    tables=bytes([int(split_strings),int(trailer)])+uvarint(len(string_bytes))
    if split_strings:tables+=b"".join(uvarint(len(s)) for s in string_bytes)+b"".join(string_bytes)
    else:tables+=b"".join(uvarint(len(s))+s for s in string_bytes)
    binary=b""
    tables += uvarint(len(uuids.items))
    binary+=b"".join(uuidlib.UUID(v).bytes for v in uuids.items)
    tables += uvarint(len(hexes.items))+b"".join(uvarint(len(h)//2) for h in hexes.items)
    binary+=b"".join(bytes.fromhex(h) for h in hexes.items)
    if not trailer:tables+=binary
    body=ints(shape_col,advanced,ef)+ints(ctx_col,advanced,ef)+ints(dt_col[1:],advanced,ef)+ints(el_col,advanced,ef)
    body+=b"".join(b"".join(tokens) for _,_,_,tokens in enc)
    tables += meta
    out = head + tables + bytes(ctx_bytes) + bytes(shape_bytes) + body
    if sections is not None:
        sections.update(header=len(head), tables=len(tables), contexts=len(ctx_bytes), shapes=len(shape_bytes),
                        coldir=0, body=len(body))
    return out, binary if trailer else b""


def decode(raw,trailer=b''):
    r=Reader(raw);u=r.u
    if r.byte()!=4 or u()!=1:raise ValueError('core version/flags')
    install=str(uuidlib.UUID(bytes=r.take(16)));first=u();n=r.count(500)
    if not n or not 1<=first<(1<<63):raise ValueError('sequence/count')
    gaps={};last=0
    for _ in range(r.count(n-1)):
        ix=u();skip=u()
        if not last<ix<n or not skip:raise ValueError('gap')
        gaps[ix]=skip;last=ix
    seqs=[first]
    for i in range(1,n):seqs.append(seqs[-1]+1+gaps.get(i,0))
    if seqs[-1]>=(1<<63):raise ValueError('sequence overflow')
    base=u();sent=r.s();split=r.byte();external=r.byte()
    if split not in (0,1) or external not in (0,1) or (not external and trailer):raise ValueError('table flags')
    ns=r.count(16000)
    if split:
        lengths=[u() for _ in range(ns)];ss=[r.take(k).decode('utf-8',errors='surrogatepass') for k in lengths]
    else:ss=[r.take(u()).decode('utf-8',errors='surrogatepass') for _ in range(ns)]
    nu=r.count(16000);nh=r.count(16000);hlens=[u() for _ in range(nh)]
    b=Reader(trailer) if external else r
    uuids=[str(uuidlib.UUID(bytes=b.take(16))) for _ in range(nu)]
    hexes=[b.take(k).hex() for k in hlens]
    if external:b.end()
    def lookup(tab,ix):
        if not 0<=ix<len(tab):raise ValueError('index')
        return tab[ix]
    def string():return lookup(ss,u())
    meta={'install_id':install,'project_id':string(),'sdk':{'name':string(),'version':string()}}
    nc=r.count(n);ctxs=[]
    for _ in range(nc):ctxs.append((str(uuidlib.UUID(bytes=r.take(16))),*[string() for _ in CTX_FIELDS[:-1]],r.s()))
    nsh=r.count(n);shapes=[];order=[];seen=set()
    for _ in range(nsh):
        name=string();fields=[];keys=set()
        for j in range(r.count(32)):
            k=string();t=r.byte()
            if k in keys or t>12 or not re.fullmatch(r'[a-z](?:[a-z0-9]|_(?!_))*[a-z0-9]|[a-z]',k) or len(k)>64:raise ValueError('shape key/type')
            if t==T_PRED and k!='placed_state_hash':raise ValueError('prediction key')
            keys.add(k)
            if t==T_ALIAS:
                ix=u()
                if ix>=j:raise ValueError('alias')
                t=(T_ALIAS,ix)
            if t==T_CTXREF and k not in CTX_FIELDS:raise ValueError('context key')
            fields.append((k,t))
            if not isinstance(t,tuple) and t not in (T_NULL,T_CTXREF) and (k,t) not in seen:order.append((k,t));seen.add((k,t))
        shapes.append((name,fields))
    shape=readints(r,n);context=readints(r,n);dt=[0]+readints(r,n-1);el=readints(r,n)
    need={key:0 for key in order}
    for sid,cid in zip(shape,context):
        lookup(ctxs,cid)
        for key in lookup(shapes,sid)[1]:
            if key in need:need[key]+=1
    columns={}
    for k,t in order:
        count=need[k,t]
        if not count:raise ValueError('unused shape')
        if t==T_INT:vals=readints(r,count)
        elif t==T_U64:vals=[u() for _ in range(count)]
        elif t==T_BOOL:vals=[bool(x) for x in readbits(r,count,1)]
        elif t in (T_F32,T_F64):vals=readfloats(r,count,4 if t==T_F32 else 8)
        elif t==T_PRED:
            bitmap=readbits(r,count,1);vals=[PRED if x else r.take(32).hex() for x in bitmap]
        else:
            mode=r.byte();tab={T_STR:ss,T_NUMTEXT:ss,T_UUID:uuids,T_HEX:hexes}[t]
            if mode==1:
                local=[lookup(tab,u()) for _ in range(r.count(count))];ids=readints(r,count);vals=[lookup(local,v) for v in ids]
            elif mode==0:vals=[lookup(tab,v) for v in readints(r,count)]
            else:raise ValueError('index mode')
            if t==T_NUMTEXT:
                vals=[Decimal(v) for v in vals]
                if not all(v.is_finite() for v in vals):raise ValueError('nonfinite decimal')
        if t==T_INT and any(not -(1<<63)<=v<(1<<63) for v in vals):raise ValueError('int domain')
        columns[k,t]=iter(vals)
    r.end();events=[];ts=base;prev={};previous_hash=None
    for i in range(n):
        ts+=dt[i];c=ctxs[context[i]];ctx=dict(zip(CTX_FIELDS,c[1:]));pe=prev.get(context[i]);elapsed=el[i] if pe is None else el[i]+pe[0]+ts-pe[1];prev[context[i]]=(elapsed,ts)
        if not 0<=ts<=253402300799999 or not -(1<<63)<=elapsed<(1<<63):raise ValueError('time domain')
        name,fields=shapes[shape[i]];props={};keys=[]
        for k,t in fields:
            if isinstance(t,tuple):v=props[keys[t[1]]]
            elif t==T_NULL:v=None
            elif t==T_CTXREF:v=ctx[k]
            else:v=next(columns[k,t])
            props[k]=v;keys.append(k)
        e={'session_id':c[0],'name':name,'ts':ts,'session_elapsed_ms':elapsed,**ctx,'properties':props,'sequence':seqs[i]}
        if 'placed_state_hash' in props:
            v=props['placed_state_hash']
            if v is PRED:
                v=hash_prediction(previous_hash,e)
                if v is None:raise ValueError('prediction before anchor')
                props['placed_state_hash']=v
            if type(v) is str and len(v)==64 and HEX_RE.fullmatch(v):previous_hash=v
        if any(type(v) is str and len(v.encode('utf-8',errors='replace'))>1024 for v in props.values()):raise ValueError('property string size')
        if len(jdump(props).encode('utf-8',errors='backslashreplace'))>8192:raise ValueError('property object size')
        events.append(e)
    meta['sent_at_ms']=ts+sent
    return meta,events
