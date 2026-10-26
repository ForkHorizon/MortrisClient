"""MTB5 research prototype: schema-aware context-modelled binary arithmetic coding of events.
One code path for encode and decode (coder.enc decides). No zstd. Model priors come from a trained
snapshot (shipped with the client like a zstd dictionary). Optional stateful mode keeps the model and
'previous values' from the last server-ACKed batch.
"""
import struct,re,copy,hashlib,time
from decimal import Decimal
import range_coder as rc
UUID_RE=re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
HEX_RE=re.compile(r'^(?:[0-9a-f]{2})+$')
DEVICE_KEYS=("app_version","build_number","platform","os_version","device_class","locale")
TABLE_MAX=255; TABLE_STRLEN=48

from model import Model,context_slot

def f32ok(x):
    try:return struct.unpack('<f',struct.pack('<f',x))[0]==x
    except OverflowError:return False

class Coder:
    def __init__(s,model,enc=True,buf=None,costs=None):
        s.m=model;s.enc=enc;s.rc=rc.Enc() if enc else rc.Dec(buf);s.P=model.probs
        s.costs=costs;s.tag=None
        s.max_decisions=20000000
        s.shadow=rc.Enc() if not enc else None
        s.sent_delta=250
        s.expected_events=None
        s.max_literal_bytes=2097152
        s.literal_bytes=0
        s.deadline=None
    def bit(s,ctx,b=None):
        if s.rc.nbits>=s.max_decisions:raise ValueError('decision budget')
        if s.deadline is not None and s.rc.nbits%512==0 and time.monotonic()>s.deadline:raise ValueError('decode deadline')
        i=context_slot(ctx,s.m.bits)*2
        pr=[s.P[i],s.P[i+1]]
        if not s.enc:
            old=pr[:];b=s.rc.bit(pr)
            s.shadow.bit(old,b)
        else:b=s.rc.bit(pr,b)
        s.P[i],s.P[i+1]=pr
        return b
    # ---- integers: Elias-gamma style; length in a binary tree, mantissa bits modelled by (len,pos[,prefix])
    def uint(s,ctx,v=None):
        if s.enc:
            L=v.bit_length()
            # length 0..127 as unary-ish binary tree of 7 bits
            node=1
            for i in range(6,-1,-1):
                b=(L>>i)&1;s.bit((ctx,'L',node),b);node=node*2+b
            pre=1
            for i in range(L-2,-1,-1):
                b=(v>>i)&1;c=(ctx,'M',L,pre) if L<=8 else (ctx,'M',L,i if i<L-4 else pre)
                s.bit(c,b)
                if L<=8 or i>=L-4:pre=pre*2+b
            return v
        node=1
        for i in range(7):node=node*2+s.bit((ctx,'L',node))
        L=node-128
        if L==0:return 0
        if L>70:raise ValueError('integer too long')
        v=1;pre=1
        for i in range(L-2,-1,-1):
            c=(ctx,'M',L,pre) if L<=8 else (ctx,'M',L,i if i<L-4 else pre)
            b=s.bit(c);v=v*2+b
            if L<=8 or i>=L-4:pre=pre*2+b
        return v
    def sint(s,ctx,v=None):
        if s.enc:
            s.uint(ctx,(v<<1) if v>=0 else ((-v)<<1)-1);return v
        z=s.uint(ctx);return (z>>1) if not z&1 else -((z+1)>>1)
    def sym(s,ctx,v=None,bits=3):
        """small symbol 0..2^bits-1 via full binary tree"""
        node=1
        for i in range(bits-1,-1,-1):
            b=s.bit((ctx,'S',node),((v>>i)&1) if s.enc else None);node=node*2+b
        return node-(1<<bits)
    def rawbits(s,ctx,v,n):
        """n bits MSB first, each modelled by (ctx,pos): learns constant bits (e.g. UUID version)"""
        out=0
        for i in range(n-1,-1,-1):
            b=s.bit((ctx,'R',i),((v>>i)&1) if s.enc else None);out=out*2+b
        return out
    def bytes_o1(s,ctx,data=None,limit=65536):
        """length + bytes with order-1 byte context (context family ctx)"""
        n=s.uint((ctx,'len'),len(data) if s.enc else None);out=bytearray();prev=0;run=0
        s.literal_bytes+=n
        if n>limit or s.literal_bytes>s.max_literal_bytes:raise ValueError('text length')
        for k in range(n):
            node=1
            for i in range(7,-1,-1):
                b=s.bit((ctx,'B',prev,run,node),((data[k]>>i)&1) if s.enc else None);node=node*2+b
            prev=node-256;out.append(prev)
            run=min(run+1,15) if (48<=prev<=57 or 65<=prev<=90 or 97<=prev<=122 or prev>=128) else 0
        return bytes(out)

# ---------------- value coding
T_NONE,T_BOOL,T_INT,T_F32,T_F64,T_STR,T_DEC=range(7)
S_TAB,S_UUID,S_HEX,S_EXT,S_TEXT,S_ALIAS=range(6)
def vtype(v):
    if v is None:return T_NONE
    if isinstance(v,bool):return T_BOOL
    if isinstance(v,int):return T_INT
    if isinstance(v,float):return T_F32 if f32ok(v) else T_F64
    if isinstance(v,Decimal):return T_DEC
    if isinstance(v,str):return T_STR
    raise ValueError('unsupported value type')

class EventCodec:
    def __init__(s,c,hash_rule=False):
        s.c=c;s.m=c.m;s.hash_rule=hash_rule
    # --- strings
    def table_add(s,field,v):
        t=s.m.tables.setdefault(field,[]);ix=s.m.tidx.setdefault(field,{})
        if v not in ix and len(t)<TABLE_MAX and len(v)<=TABLE_STRLEN and s.m.table_bytes+len(v.encode('utf-8','surrogatepass'))<=1048576 and s.m.table_entries<8192:
            ix[v]=len(t);t.append(v);s.m.table_bytes+=len(v.encode('utf-8','surrogatepass'));s.m.table_entries+=1
    def string(s,field,v=None,alias=None,key=None,limit=65536):
        c=s.c;enc=c.enc;last=s.m.last.get(('s',field))
        klast=s.m.last.get(('sk',key)) if key is not None else None
        if klast is not None:
            if c.bit((field,'eqklast'),(v==klast) if enc else None):
                s.m.last[('s',field)]=klast;return klast
        if last is not None and last!=klast:
            if c.bit((field,'eqlast'),(v==last) if enc else None):return last
        if alias is not None and alias!=last:
            if c.bit((field,'alias'),(v==alias) if enc else None):
                s.m.last[('s',field)]=alias;return alias
        t=s.m.tables.get(field,[]);ix=s.m.tidx.get(field,{})
        if enc:
            if v in ix:st=S_TAB
            elif UUID_RE.match(v):st=S_UUID
            elif HEX_RE.match(v) and len(v)>=16:st=S_HEX
            elif last is not None and len(v)>len(last) and v.startswith(last):st=S_EXT
            elif last is not None and len(last)>=16 and _edit_gain(last,v):st=S_ALIAS
            else:st=S_TEXT
        st=c.sym((field,'st'),st if enc else None,3)
        if st==S_TAB:
            i=c.uint((field,'tab'),ix[v] if enc else None)
            if i>=len(t):raise ValueError('table index')
            v=t[i]
        elif st==S_UUID:
            x=c.rawbits(('uuid',),int(v.replace('-',''),16) if enc else None,128)
            h='%032x'%x;v=f'{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}'
        elif st==S_HEX:
            n=c.uint((field,'hexlen'),len(v)//2 if enc else None)
            if n>min(32768,limit//2):raise ValueError('hex length')
            x=c.rawbits(('hex',),int(v,16) if enc else None,8*n) if n else 0
            v=('%0*x'%(2*n,x)) if n else ''
        elif st==S_EXT:
            if last is None:raise ValueError('ext without last')
            tail=c.bytes_o1(('txt',),v[len(last):].encode('utf-8','surrogatepass') if enc else None)
            v=last+tail.decode('utf-8','surrogatepass')
        elif st==S_TEXT:
            v=c.bytes_o1(('txt',),v.encode('utf-8','surrogatepass') if enc else None,limit=limit).decode('utf-8','surrogatepass')
            s.table_add(field,v)
        elif st==S_ALIAS:  # edit against previous value of this field
            if last is None:raise ValueError('edit without last')
            v=s.edit(field,last,v)
        else:raise ValueError('string subtype')
        if len(v.encode('utf-8','surrogatepass'))>limit:raise ValueError('string domain')
        s.m.last[('s',field)]=v;return v
    def edit(s,field,last,v):
        c=s.c;enc=c.enc;a=last.encode('utf-8','surrogatepass')
        b=v.encode('utf-8','surrogatepass') if enc else None
        if enc:
            same=len(a)==len(b)
            diffs=[i for i in range(len(a)) if a[i]!=b[i]] if same else None
            mode=1 if same and len(diffs)*4<=len(a) else 0
        mode=c.bit((field,'edmode'),mode if enc else None)
        if mode:  # substitutions at positions, same length
            k=c.uint((field,'edn'),len(diffs) if enc else None);out=bytearray(a);pos=-1
            if k>len(a):raise ValueError('edit count')
            for j in range(k):
                g=c.uint((field,'edgap'),(diffs[j]-pos-1) if enc else None);pos+=g+1
                if pos>=len(out):raise ValueError('edit pos')
                node=1;old_byte=out[pos]
                for i in range(7,-1,-1):
                    bt=c.bit((field,'edb',old_byte,node),((b[pos]>>i)&1) if enc else None);node=node*2+bt
                out[pos]=node-256
            r=bytes(out)
        else:     # common prefix / suffix + literal middle
            if enc:
                p=0
                while p<min(len(a),len(b)) and a[p]==b[p]:p+=1
                q=0
                while q<min(len(a),len(b))-p and a[-1-q]==b[-1-q]:q+=1
            p=c.uint((field,'edp'),p if enc else None);q=c.uint((field,'edq'),q if enc else None)
            if p+q>len(a):raise ValueError('edit span')
            mid=c.bytes_o1(('txt',),b[p:len(b)-q] if enc else None)
            r=a[:p]+mid+a[len(a)-q:]
        return r.decode('utf-8','surrogatepass')
    # --- ints with backward-adaptive predictor choice
    def integer(s,field,v,key,name,ts):
        c=s.c;L=s.m.last;p0=L.get(('i',key));p1=L.get(('i',key,name))
        cands=[]
        pe=s._prev;pp=pe['properties'] if pe else {}
        dtv=(ts-pe['ts']) if pe else 0
        pk=s.m.ema.get(('ptb',field));partner=pp.get(pk) if pk is not None else None
        if type(partner) is not int:partner=None
        if p0 is not None:
            v0,t0,prev0=p0
            cands=[('last',v0),('lastname',p1[0] if p1 else v0),('time',v0+(ts-t0)),('lin',2*v0-prev0),('dt',dtv),('partner',partner if partner is not None else v0)]
        if not cands:
            out=c.sint((field,'lit'),v)
        else:
            # pick predictor with lowest running cost estimate (both sides compute the same)
            best=min(range(len(cands)),key=lambda i:(s.m.ema.get((field,i),0),i))
            pred=cands[best][1]
            out=pred+c.sint((field,'res',best),(v-pred) if c.enc else None)
            for i,(_,pv) in enumerate(cands):
                e=s.m.ema.get((field,i),0);s.m.ema[(field,i)]=e+((abs(out-pv).bit_length()*16-e)//4)
        # learn which int field of the previous event usually equals this one (backward adaptive)
        best=None;bs=-1.0
        for k2,x in pp.items():
            if type(x) is not int:continue
            old=s.m.ema.get(('pts',field,k2),0);sc=old-((old+9)//10)+(1024 if x==out else 0);s.m.ema[('pts',field,k2)]=sc
            if sc>bs:best,bs=k2,sc
        if best is not None:s.m.ema[('ptb',field)]=best
        prev=p0[0] if p0 else out
        L[('i',key)]=(out,ts,prev);L[('i',key,name)]=(out,ts,prev)
        return out
    def flt(s,field,v,t):
        c=s.c;last=s.m.last.get(('f',field))
        if last is not None and c.bit((field,'feq'),(struct.pack('<d',v)==struct.pack('<d',last)) if c.enc else None):return last
        if t==T_F32:
            x=struct.unpack('<I',struct.pack('<f',v))[0] if c.enc else 0
            se=c.uint((field,'se32'),x>>23 if c.enc else None)  # sign+exponent (9 bits) modelled
            if se>=512 or (se&0xFF)==0xFF:raise ValueError('f32 exponent')
            m=c.rawbits((field,'m32'),x&0x7FFFFF,23);x=(se<<23)|m
            out=struct.unpack('<f',struct.pack('<I',x))[0]
        else:
            x=struct.unpack('<Q',struct.pack('<d',v))[0] if c.enc else 0
            se=c.uint((field,'se64'),x>>52 if c.enc else None)
            if se>=4096 or (se&0x7FF)==0x7FF:raise ValueError('f64 exponent')
            m=c.rawbits((field,'m64'),x&((1<<52)-1),52);x=(se<<52)|m
            out=struct.unpack('<d',struct.pack('<Q',x))[0]
        s.m.last[('f',field)]=out;return out
    def value(s,name,key,v,ts,prev_str,prev_hash):
        c=s.c;enc=c.enc;field=(name,key)
        t=c.sym((field,'type'),vtype(v) if enc else None,3)
        if t==T_NONE:return None
        if t==T_BOOL:
            lb=s.m.last.get(('b',field),0)
            b=c.bit((field,'bool',lb),int(v) if enc else None);s.m.last[('b',field)]=b;return bool(b)
        if t==T_INT:
            if enc and not (-(1<<63)<=v<(1<<64)):raise ValueError('int domain')
            out=s.integer(field,v,key,name,ts)
            if not -(1<<63)<=out<(1<<64):raise ValueError('int domain')
            return out
        if t in (T_F32,T_F64):return s.flt(field,v,t)
        if t==T_DEC:
            txt=s.c.bytes_o1(('dec',),str(v).encode() if enc else None).decode()
            try:
                value=Decimal(txt)
                if not value.is_finite():raise ValueError('decimal finite')
                return value
            except Exception as ex:raise ValueError('decimal') from ex
        if t==T_STR:
            if s.hash_rule and key=='placed_state_hash' and prev_hash is not None:
                pred=hash_pred(prev_hash,name,s._props)
                if pred is not None and c.bit((field,'hpred'),(v==pred) if enc else None):
                    s.m.last[('s',field)]=pred;s.m.last[('sk',key)]=pred;return pred
            out=s.string(field,v,alias=prev_str,key=key,limit=1024);s.m.last[('sk',key)]=out;return out
        raise ValueError('type')

def _edit_gain(a,b):
    a=a.encode('utf-8','surrogatepass');b=b.encode('utf-8','surrogatepass')
    if len(a)==len(b):
        d=sum(1 for x,y in zip(a,b) if x!=y)
        if d*4<=len(a):return True
    p=0
    while p<min(len(a),len(b)) and a[p]==b[p]:p+=1
    q=0
    while q<min(len(a),len(b))-p and a[-1-q]==b[-1-q]:q+=1
    return p+q>=8

def hash_pred(prev,name,p):
    """Synthetic generator's game rule (same as V4 HASH_PRED); only for the separate 'game-rule' row."""
    if not isinstance(prev,str) or not re.fullmatch(r'[0-9a-f]{64}',prev):return None
    if name=='placement_resolved' and p.get('outcome')=='placed':
        xyz=[p.get(k) for k in ('block_id','cell_x','cell_y')]
        if any(type(x) is not int or not 0<=x<=255 for x in xyz):return None
        return hashlib.sha256(prev.encode('ascii')+bytes(xyz)).hexdigest()
    return prev

def code_batch(c,inst_id,batch,stateful=False,hash_rule=False):
    """Encode (c.enc) or decode a batch. Returns (install_id, events)."""
    m=c.m;enc=c.enc;E=EventCodec(c,hash_rule)
    if not stateful:m.reset_batch_state()
    L=m.last
    if not stateful or ('install',) not in L:
        inst_id=E.string(('hdr','install'),inst_id);L[('install',)]=inst_id
    else:inst_id=L[('install',)]
    n=c.uint(('hdr','n'),len(batch) if enc else None)
    if not 1<=n<=500 or (c.expected_events is not None and c.expected_events!=n):raise ValueError('n')
    out=[]
    for k in range(n):
        e=batch[k] if enc else None;prev=L.get(('ev',))
        pname=prev['name'] if prev else None
        c.tag='name';name=E.string(('name',pname),e['name'] if enc else None,limit=64)
        c.tag='session';sid=E.string(('session',),e['session_id'] if enc else None)
        c.tag='ts'
        if prev is None:ts=c.uint(('ts0',),e['ts'] if enc else None)
        else:ts=prev['ts']+c.sint(('dt',pname,name),(e['ts']-prev['ts']) if enc else None)
        c.tag='elapsed';same=prev is not None and prev['session_id']==sid
        if same:
            pe=prev['session_elapsed_ms'];pp=L.get(('pel',),pe)
            cands=[pe+(ts-prev['ts']),2*pe-pp]
            bi=min(range(2),key=lambda i:(m.ema.get(('el',i),0),i));pred=cands[bi]
            el=pred+c.sint(('el',name,bi),(e['session_elapsed_ms']-pred) if enc else None)
            for i in range(2):
                x=m.ema.get(('el',i),0);m.ema[('el',i)]=x+((abs(el-cands[i]).bit_length()*16-x)//4)
        else:el=c.sint(('el0',name),e['session_elapsed_ms'] if enc else None)
        L[('pel',)]=prev['session_elapsed_ms'] if same else el
        c.tag='sequence'
        if prev is None:seq=c.uint(('seq0',),e['sequence'] if enc else None)
        else:seq=prev['sequence']+1+c.sint(('dseq',),(e['sequence']-prev['sequence']-1) if enc else None)
        c.tag='device';ev={}
        if enc and 'event_id' in e:pass
        dev={}
        for key in DEVICE_KEYS:dev[key]=E.string(('dev',key),e[key] if enc else None)
        tz=L.get(('tz',));
        if tz is None:tz=c.sint(('tz0',),e['timezone_offset_minutes'] if enc else None)
        else:tz=tz+c.sint(('dtz',),(e['timezone_offset_minutes']-tz) if enc else None)
        L[('tz',)]=tz
        # property shape
        c.tag='shape';keys=list(e['properties'].keys()) if enc else None;last_shape=L.get(('shape',name))
        if last_shape is not None and c.bit(('shape_eq',name),(keys==last_shape) if enc else None):keys=last_shape
        else:
            nk=c.uint(('nk',name),len(keys) if enc else None);kk=[];pk=None
            if nk>32:raise ValueError('key count')
            for j in range(nk):pk=E.string(('key',name,pk),keys[j] if enc else None,limit=64);kk.append(pk)
            if len(set(kk))!=len(kk):raise ValueError('dup key')
            keys=kk
        L[('shape',name)]=keys
        props={};E._props=props;E._prev=prev;prev_str=None
        for key in keys:
            c.tag=('prop',key)
            v=E.value(name,key,e['properties'][key] if enc else None,ts,prev_str,L.get(('hash',)))
            props[key]=v
            if isinstance(v,str):
                prev_str=v
                if key=='placed_state_hash':L[('hash',)]=v
        if prev is not None and prev['session_id']!=sid:L.pop(('hash',),None)
        ev=dict(session_id=sid,name=name,ts=ts,session_elapsed_ms=el,**dev,timezone_offset_minutes=tz,properties=props,sequence=seq)
        validate_event(ev)
        L[('ev',)]=ev;out.append(ev)
        m.check_budget()
    # sent_at delta (render currently derives it; coded anyway for fairness with V4's sent_delta field)
    c.tag='sent';c.sent_delta=c.sint(('sent',),c.sent_delta if enc else None)
    return inst_id,out


def validate_event(e):
    from support import wire
    if not re.fullmatch(r'[a-z](?:[a-z0-9]|_(?!_))*[a-z0-9]|[a-z]',e['name']) or len(e['name'])>64:raise ValueError('event name')
    if not 1<=e['sequence']<(1<<63) or not 0<=e['ts']<=253402300799999 or not -(1<<63)<=e['session_elapsed_ms']<(1<<63):raise ValueError('event range')
    p=e['properties']
    for k,v in p.items():
        if len(k)>64 or not re.fullmatch(r'[a-z](?:[a-z0-9]|_(?!_))*[a-z0-9]|[a-z]',k):raise ValueError('key')
        if type(v) is str and len(v.encode('utf-8',errors='replace'))>1024:raise ValueError('property string')
    if len(wire.jdump(p).encode('utf-8',errors='backslashreplace'))>8192:raise ValueError('properties size')
