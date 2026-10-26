"""Inspect the already cloned emulator SQLite; no device writes/network here."""
import gzip,hashlib,json,sqlite3
from datetime import datetime
from support7 import ROOT,v6,wire,z
from transport7 import Catalog,Aliases,shape,encode,decode
from game_cleanup import clean_properties

def run():
    path=ROOT/'results/private/emulator-daliys_analytics.db'
    db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
    raw=[r[0]for r in db.execute('select payload_json from pending_events order by sequence')]
    origin=db.execute("select value from metadata where key='install_id'").fetchone()[0];db.close()
    rows=[json.loads(s)for s in raw];events=[]
    for row in rows:
        e={k:row[k]for k in ('event_id','session_id','name','sequence','session_elapsed_ms',*wire.DEVICE_KEYS,'properties')}
        e['ts']=round(datetime.fromisoformat(row['occurred_at_client']).timestamp()*1000);events.append(e)
    if not events:return
    catalog=Catalog.load((ROOT/'results/catalog-real-raw.json').read_bytes())
    dictionary=z.ZstdCompressionDict((ROOT/'results/dict-real-raw-16384.bin').read_bytes())
    unknown=sum(shape(e)not in catalog.ids for e in events)
    normalized=[]
    for e in events:
        current=shape(e);candidates=[s for s in catalog.shapes if s[0]==e['name']and set(s[1])==set(current[1])]
        if not candidates:continue
        normalized.append(dict(e,properties={k:e['properties'][k]for k,_ in candidates[0][1]}))
    a=Aliases(bytes(8));a.register(origin,events)
    framebytes=None
    if len(normalized)==len(events):
        f=encode(catalog,a,origin,normalized,dictionary,True);o,ev=decode(catalog,a,f,dictionary,authorized_project=catalog.project,authorized_origin=origin)
        assert ev==normalized and o==origin;framebytes=len(f)
    # Use exact queued event JSON strings in the reconstructed envelope.
    def body(strings):
        head={'schema_version':1,'project_id':'puzzle_gravity_test','install_id':origin,'sdk':{'name':'mortris-unity','version':'0.2.0'},'sent_at_client':wire.iso_ms(events[-1]['ts']+250)}
        prefix=json.dumps(head,separators=(',',':'))[:-1]
        return (prefix+',"events":['+','.join(strings)+']}').encode()
    source=body(raw);cleanrows=[]
    for row in rows:cleanrows.append(json.dumps(dict(row,properties=clean_properties(row['properties'],migrate_interactions=True)),separators=(',',':'),ensure_ascii=False))
    cleaned=body(cleanrows)
    result={'source':'cloned idle emulator1.1.14 SQLite, exact queued event JSON; reconstructed request envelope','events':len(events),
            'source_sha256':hashlib.sha256(source).hexdigest(),'v1_json_bytes':len(source),'v1_gzip1_bytes':len(gzip.compress(source,1,mtime=0)),
            'clean_json_bytes':len(cleaned),'clean_gzip1_bytes':len(gzip.compress(cleaned,1,mtime=0)),
            'catalog_order_mismatch_events':unknown,'canonical_order_mapped_events':len(normalized),
            'full_uuid_v7_dict16_bytes_after_order_normalization':framebytes,'Android_V7_CPU_GC_measured':False}
    (ROOT/'results/emulator-queue.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':run()
