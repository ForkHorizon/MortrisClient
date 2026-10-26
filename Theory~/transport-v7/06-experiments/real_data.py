"""Read the private read-only PostgreSQL COPY snapshot. Never access prod here."""
import gzip, hashlib, json
from collections import Counter, defaultdict
from datetime import datetime
from types import SimpleNamespace
from support7 import ROOT, wire

DUMP = ROOT / 'results/private/puzzle-2026-10-16.jsonl.gz'

def load():
    selected=defaultdict(list); counts=Counter(); builds=Counter();names=Counter();installs=set();sessions=set()
    interactions=defaultdict(set);indices=defaultdict(set)
    with gzip.open(DUMP,'rt') as f:
        for line in f:
            # COPY text escapes every JSON backslash once; JSON contains no literal tabs/newlines.
            e=json.loads(line.rstrip('\n').replace('\\\\','\\'))
            p=e['properties'];origin=e['install_id'];installs.add(origin);sessions.add(e['session_id']);names[e['name']]+=1
            counts['events']+=1;builds[(e['app_version'],e['build_number'])]+=1
            if 'wave_attempt_id' in p:
                counts['wave_alias_present']+=1;counts['wave_alias_mismatch']+=p.get('attempt_id')!=p['wave_attempt_id']
            if 'placed_state_hash' in p:
                counts['hash_present']+=1
                ids=p.get('placed_block_ids')
                if type(ids) is str:
                    counts['hash_with_csv']+=1;counts['hash_mismatch']+=hashlib.sha256(ids.encode()).hexdigest()!=p['placed_state_hash']
                else:counts['hash_without_csv']+=1
                counts['truncated']+=bool(p.get('placed_block_ids_truncated'))
            iid=p.get('interaction_id')
            if iid:
                counts['interaction_present']+=1
                if not p.get('attempt_id') or type(p.get('interaction_index')) is not int or p['interaction_index']<=0:counts['interaction_missing_pair']+=1
                else:
                    key=(origin,p['attempt_id'],p['interaction_index']);interactions[key].add(iid)
                    indices[(origin,iid)].add((p['attempt_id'],p['interaction_index']))
            # Bounded per-install selection is deterministic; installs split before training.
            if len(selected[origin])>=600:continue
            event={k:e[k] for k in ('event_id','session_id','sequence','session_elapsed_ms','name',*wire.DEVICE_KEYS)}
            event['properties']=p;event['ts']=round(datetime.fromisoformat(e['occurred_at_client']).timestamp()*1000)
            selected[origin].append(event)
    counts['pair_collision']=sum(len(x)>1 for x in interactions.values())
    counts['id_has_multiple_pairs']=sum(len(x)>1 for x in indices.values())
    train=[];holdout=[]
    for origin,events in sorted(selected.items()):
        events.sort(key=lambda e:e['sequence'])
        # Duplicate sequence origins cannot use sequence identity; preserve them for audit.
        if len({e['sequence'] for e in events})!=len(events):counts['duplicate_sequence_installs']+=1;continue
        ds=(SimpleNamespace(install_id=origin),[events[i:i+100] for i in range(0,len(events),100)])
        (train if int(hashlib.sha256(origin.encode()).hexdigest(),16)%5==0 else holdout).append(ds)
    report={'source':'production DB rows; natural/player labels are producer assertions, not independent human-traffic proof',
            'received_day_utc':'2026-10-16','dump_sha256':hashlib.sha256(DUMP.read_bytes()).hexdigest(),
            'dump_compressed_bytes':DUMP.stat().st_size,'counts':dict(counts),'installs':len(installs),'sessions':len(sessions),
            'event_names':dict(names),'builds':[{'app_version':a,'build_number':b,'events':n} for (a,b),n in builds.items()],
            'sample_limit_per_install':600,'train_installs':len(train),'holdout_installs':len(holdout),
            'train_events':sum(len(b) for _,bs in train for b in bs),'holdout_events':sum(len(b) for _,bs in holdout for b in bs),
            'split':'sha256(install_id) % 5 == 0 for training; all other installs held out; first600 per install',
            'wire_reconstruction':'DB jsonb reorders properties; HTTP boundaries, exact JSON lexemes and SDK envelope not stored. Reconstructed 100-event body is not original HTTP capture.'}
    (ROOT/'results/real-audit.json').write_text(json.dumps(report,indent=2))
    return train,holdout

if __name__=='__main__':
    train,test=load();print(json.dumps({'train_installs':len(train),'test_installs':len(test)},indent=2))
