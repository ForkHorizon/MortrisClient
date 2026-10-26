"""Executable request/row binding model, separate from product SDK."""
import sqlite3
from primitives import Reader,u
class Queue:
    def __init__(self):
        self.db=sqlite3.connect(':memory:');self.db.execute('create table q(id integer primary key, payload blob)');self.requests={}
    def enqueue(self,ids):self.db.executemany('insert into q values(?,?)',[(x,b'x') for x in ids]);self.db.commit()
    def send(self,token,ids):
        if token in self.requests or len(set(ids))!=len(ids):raise ValueError('request identity')
        self.requests[token]=tuple(ids)
    def timeout(self,token):self.requests.pop(token,None)
    def ack(self,token,body):
        if token not in self.requests:return []
        ids=self.requests[token];r=Reader(body);control=r.byte();r.u()
        if control not in (0x40,0x41,0x42,0x43):raise ValueError('ack control')
        exceptions=[]
        if control==0x41:
            prev=-1
            for _ in range(r.count(len(ids))):
                ix=r.u();reason=r.u()
                if not prev<ix<len(ids) or reason not in (1,2,3):raise ValueError('ack exceptions')
                exceptions.append(ix);prev=ix
        r.end()
        accepted=[] if control in (0x42,0x43) else [v for i,v in enumerate(ids) if i not in exceptions]
        with self.db:self.db.executemany('delete from q where id=?',[(v,) for v in accepted])
        del self.requests[token];return accepted
    def pending(self):return [x[0] for x in self.db.execute('select id from q order by id')]

class Server:
    """Durable identity model: cold per-event digest remains authoritative."""
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.execute('create table if not exists events(origin text,seq integer,digest blob,primary key(origin,seq))')
    def commit(self,authorized_origins,origin,events):
        if origin not in authorized_origins:raise ValueError('origin authorization')
        accepted=[]
        with self.db:
            for seq,digest in events:
                old=self.db.execute('select digest from events where origin=? and seq=?',(origin,seq)).fetchone()
                if old and old[0]!=digest:raise ValueError('identity conflict')
                if not old:self.db.execute('insert into events values(?,?,?)',(origin,seq,digest))
                accepted.append(seq)
        # ACK is returned only after transaction context commits.
        return accepted
