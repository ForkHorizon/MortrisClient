"""Isolated SQLite payload storage experiment; not a queue migration implementation."""
import json,sqlite3,tempfile,time,sys
from pathlib import Path
import msgpack,zstandard as z
import core,wire
from workloads import make
ROOT=Path(__file__).resolve().parent
out={}
for name in ['base','rich','alt']:
 i,bs=make(name,101,1)[0];rows=[wire.jdump(wire.v1_event(e)).encode() for b in bs for e in b]
 tr=make(name,202,3);samples=[wire.jdump(wire.v1_event(e)).encode() for _,bs in tr for b in bs for e in b]
 d=z.train_dictionary(16384,samples);c=z.ZstdCompressor(level=3,dict_data=d);de=z.ZstdDecompressor(dict_data=d)
 packed=[msgpack.packb(json.loads(r),use_bin_type=True) for r in rows]
 for a,b in zip(rows,packed):assert wire.jdump(msgpack.unpackb(b,raw=False)).encode()==a
 zipped=[c.compress(r) for r in rows]
 assert [de.decompress(b) for b in zipped]==rows
 chunks=[]
 for k in range(0,len(rows),50):
  joined=msgpack.packb(rows[k:k+50],use_bin_type=True);blob=c.compress(joined);assert msgpack.unpackb(de.decompress(blob),raw=False)==rows[k:k+50];chunks.append(blob)
 row={}
 for label,values in [('json',rows),('msgpack64',packed),('zstd3_dict16_rows',zipped),('chunks50_zstd3_dict16',chunks)]:
  with tempfile.TemporaryDirectory() as td:
   dbfile=Path(td)/'q.db';db=sqlite3.connect(dbfile);db.execute('pragma journal_mode=WAL');db.execute('create table q(id integer primary key,payload blob not null)');db.executemany('insert into q(payload) values(?)',[(b,) for b in values]);db.commit()
   before={p.name:p.stat().st_size for p in Path(td).iterdir()};db.execute('pragma wal_checkpoint(TRUNCATE)');db.close()
   row[label]={'payload_bytes':sum(map(len,values)),'db_bytes_checkpointed':dbfile.stat().st_size,'files_before_checkpoint':before,'rows':len(values),'events':len(rows),'dictionary_bytes':16384 if 'zstd' in label else 0}
 out[name]=row
(ROOT/'results/queue-storage.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
