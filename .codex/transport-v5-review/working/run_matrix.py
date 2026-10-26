import json,sys,pickle,zlib
from evalctx import *
import ctxcodec as cc
name=sys.argv[1];rows=[]
def emit(r):print(r,flush=True);rows.append(r)
if name=='drift':
    snap=train('drift',0)
    for sf in (False,True):emit(evaluate('drift','hold909',0,snap,stateful=sf))
    snapb=train('base',100)  # prior from a different product profile (mismatch test)
    emit({**evaluate('drift','hold909',0,snapb),'note':'prior trained on base, not drift'})
else:
    for cap in (0,100,500):
        snap=train(name,cap)
        tests=[('test101',cap)]+([('hold909',100)] if cap==100 else [])
        for test,cp in tests:
            for sf in (False,True):emit(evaluate(name,test,cp,snap,stateful=sf))
        if cap==100:
            emit({**evaluate(name,'test101',100,cc.Model()),'note':'no prior (empty model)'})
            emit({'profile':name,'prior_contexts':len(snap.probs),'prior_tables':sum(len(t) for t in snap.tables.values()),
                  'prior_pickle_zlib_bytes':len(zlib.compress(pickle.dumps((snap.probs,snap.tables,snap.ema)),9))})
        if name=='base':
            sh=train(name,cap,hash_rule=True)
            for sf in (False,True):emit(evaluate(name,'test101',cap,sh,stateful=sf,hash_rule=True))
json.dump(rows,open(f'results/mtb5_{name}.json','w'),indent=1)
