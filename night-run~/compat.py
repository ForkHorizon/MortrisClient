import json,re,collections,statistics
names=collections.Counter(); st=collections.Counter(); n=0
props_n=[]; sizes=[]; maxstr=[]
fb_name=re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,39}$')
for line in open('work/batches.jsonl'):
    d=json.loads(line)
    for e in d['events']:
        n+=1; p=e['properties']; names[e['name']]+=1
        props_n.append(len(p)); sizes.append(len(json.dumps(p,separators=(',',':'))))
        longest=max([len(v) for v in p.values() if isinstance(v,str)] or [0]); maxstr.append(longest)
        if not fb_name.match(e['name']): st['fb_bad_event_name']+=1
        if len(p)>25: st['fb_gt25_params']+=1
        if any(len(k)>40 or not fb_name.match(k) for k in p): st['fb_bad_param_name']+=1
        if longest>100: st['fb_string_gt100_truncated']+=1
        if any(isinstance(v,bool) for v in p.values()): st['has_bool']+=1
        if any(v=='' for v in p.values()): st['has_empty_string']+=1
        if any(isinstance(v,str) and len(v)>256 for v in p.values()): st['string_gt256']+=1
        if any(isinstance(v,(dict,list)) for v in p.values()): st['nested']+=1
        if any(isinstance(v,float) for v in p.values()): st['has_float']+=1
        if any(v is None for v in p.values()): st['has_null']+=1
q=lambda v,x: sorted(v)[int(x*(len(v)-1))]
out={'events':n,'distinct_event_names':len(names),'top_events':names.most_common(12),'props_per_event':{'mean':statistics.mean(props_n),'p50':q(props_n,.5),'p95':q(props_n,.95),'max':max(props_n)},
 'props_json_bytes':{'mean':statistics.mean(sizes),'p50':q(sizes,.5),'p95':q(sizes,.95),'max':max(sizes)},'longest_string_value':{'p50':q(maxstr,.5),'p95':q(maxstr,.95),'p99':q(maxstr,.99),'max':max(maxstr)},
 'events_affected_by_rule':dict(st),'share_pct':{k:round(100*v/n,2) for k,v in st.items()}}
json.dump(out,open('results/data/compat.json','w'),indent=1); print(json.dumps(out,indent=1))
