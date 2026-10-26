"""Locate lossless generic integer-column gains on the unchanged private day.
No field names enter the proposed numeric codec. Original V7 stays frozen.
"""
from collections import Counter,defaultdict
import json
from support7 import ROOT,v6,core,z
from real_data import load
from game_cleanup import cleaned

from numeric7 import options as integer_options
MIN,MAX=-(1<<63),(1<<63)-1

def run():
    train,test=load();results=[]
    for variant,ds in [('raw',test),('clean',cleaned(test,migrate_interactions=True))]:
        counts=Counter();fields=defaultdict(Counter);n=0
        for _,bs in ds:
            for batch in bs:
                n+=len(batch);columns=defaultdict(list)
                for e in batch:
                    for key,value in e['properties'].items():
                        if core._vtype(value)==core.T_INT:columns[key].append((value,e))
                for key,pairs in columns.items():
                    values=[p[0]for p in pairs];owners=[p[1]for p in pairs]
                    options=integer_options(values,owners)
                    mode=min(options,key=lambda m:(len(options[m]),m));base=len(options[0]);candidate=len(options[mode])+1
                    fields[key]['baseline_raw_bytes']+=base;fields[key]['candidate_raw_bytes']+=candidate
                    fields[key]['mode_'+str(mode)]+=1
                    counts['baseline_raw_bytes']+=base;counts['candidate_raw_bytes']+=candidate
        result={'variant':variant,'events':n,'integer_baseline_raw_B_event':counts['baseline_raw_bytes']/n,
                'candidate_raw_B_event':counts['candidate_raw_bytes']/n,
                'raw_saving_B_event':(counts['baseline_raw_bytes']-counts['candidate_raw_bytes'])/n,
                'fields':dict(sorted(fields.items(),key=lambda kv:kv[1]['baseline_raw_bytes']-kv[1]['candidate_raw_bytes'],reverse=True))}
        results.append(result);print(variant,'raw numeric saving',result['raw_saving_B_event'],flush=True)
    (ROOT/'results/integer-probe.json').write_text(json.dumps(results,indent=2))
if __name__=='__main__':run()
