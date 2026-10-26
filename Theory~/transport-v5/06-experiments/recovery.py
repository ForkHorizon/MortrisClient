"""Executable failure model, not HTTP/JNI integration. ACK carries candidate state ID."""
import hashlib,json,sqlite3
from collections import OrderedDict
from support import Reader,exact
from model import Model
from frame_v5 import decode,encode

def metadata(frame):
    import uuid
    r=Reader(frame);kind=r.byte();r.byte();r.u();r.u();r.u();origin=str(uuid.UUID(bytes=r.take(16)));state=r.take(16) if kind==0x52 else None
    return origin,state

def event_sources(source):
    # Preserve event number lexemes/escapes; JSON raw_decode only locates spans.
    text=source.decode('utf-8');decoder=json.JSONDecoder();pos=0
    def ws(i):
        while i<len(text) and text[i].isspace():i+=1
        return i
    pos=ws(pos)
    if text[pos]!='{':raise ValueError('envelope')
    pos+=1
    while True:
        pos=ws(pos)
        if text[pos]=='}':break
        key,end=decoder.raw_decode(text,pos);pos=ws(end)
        if text[pos]!=':':raise ValueError('member')
        pos=ws(pos+1)
        if key=='events':
            if text[pos]!='[':raise ValueError('events')
            pos+=1;out=[]
            while True:
                pos=ws(pos)
                if text[pos]==']':return out
                _,end=decoder.raw_decode(text,pos);out.append(text[pos:end].encode('utf-8'));pos=ws(end)
                if text[pos]==',':pos+=1
                elif text[pos]!=']':raise ValueError('array')
        else:_,pos=decoder.raw_decode(text,pos)
        pos=ws(pos)
        if text[pos]==',':pos+=1
        elif text[pos]!='}':raise ValueError('object')
    raise ValueError('events missing')
class MissingBase(ValueError):pass
class Server:
    def __init__(self,prior,path,origins,capacity=2):
        self.prior=prior;self.origins=set(origins);self.capacity=capacity;self.states=OrderedDict();self.responses=OrderedDict();self.db=sqlite3.connect(path)
        self.db.execute('create table if not exists e(origin text,seq integer,digest blob,source blob,primary key(origin,seq))')
    def receive(self,frame):
        origin,ref=metadata(frame)
        if origin not in self.origins:raise ValueError('origin authorization')
        request=hashlib.sha256(frame).digest()
        if request in self.responses:return self.responses[request]
        base=self.states.get(ref) if ref is not None else None
        if ref is not None and base is None:raise MissingBase('409 missing base')
        source,candidate=decode(self.prior,frame,base=base)
        obj=json.loads(source);project=obj['project_id'];state=candidate.state_id()
        with self.db:
            for raw in event_sources(source):
                event=json.loads(raw);seq=event['sequence'];digest=exact.digest(project,origin,raw)
                old=self.db.execute('select digest from e where origin=? and seq=?',(origin,seq)).fetchone()
                if old and old[0]!=digest:raise ValueError('identity conflict')
                if not old:self.db.execute('insert into e values(?,?,?,?)',(origin,seq,digest,raw))
        # Publish only after durable DB transaction; on failure the base is untouched.
        self.states[state]=candidate
        while len(self.states)>self.capacity:self.states.popitem(last=False)
        ack=b'\x50\x01'+state;self.responses[request]=ack
        while len(self.responses)>8:self.responses.popitem(last=False)
        return ack
class Client:
    def __init__(self,prior,origin):self.prior=prior;self.origin=origin;self.state=None;self.pending=None;self.acked=[]
    def begin(self,token,batch,force_stateless=False):
        if self.pending is not None:raise ValueError('one in flight')
        frame,candidate=encode(self.prior,self.origin,batch,base=None if force_stateless else self.state)
        self.pending=(token,tuple(e['sequence'] for e in batch),candidate,frame);return frame
    def timeout(self,token):
        if self.pending and self.pending[0]==token:self.pending=None
    def ack(self,token,body):
        if self.pending is None or self.pending[0]!=token:return False
        _,rows,candidate,frame=self.pending
        if len(body)!=18 or body[:2]!=b'\x50\x01' or body[2:]!=candidate.state_id():raise ValueError('ACK binding/state')
        self.state=candidate;self.acked.extend(rows);self.pending=None;return True
