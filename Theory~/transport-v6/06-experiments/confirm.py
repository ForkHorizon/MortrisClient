"""Fresh seed2601 and batch-size/cold-session sensitivity; no prior retuning."""
import json
from codec import *
from support import ROOT, make, rebatch, drift

out={}
for profile in ('base','rich','alt','drift'):
    schema=Schema(json.loads((ROOT/'results'/f'schema-{profile}.json').read_text()))
    ds=drift(2601,1,120) if profile=='drift' else make(profile,2601,1)
    rows={}
    for cap in (1,7,100):
        client,server=Aliases(epoch=b'confirm6'),Aliases()
        total=setup=n=nb=strict=replay=0
        for inst,batches in rebatch(ds,cap,session=True):
            for b in batches:
                registration=client.register(inst.install_id,b)
                if registration:
                    server.accept(registration)
                    setup+=len(registration)+8+len(u(len(client.records)))
                f=encode(schema,client,inst.install_id,b)
                assert decode(schema,server,f,authorized_origin=inst.install_id)==render(inst.install_id,b)
                fs=encode(schema,client,inst.install_id,b,preserve_ids=True)
                assert decode(schema,server,fs,authorized_origin=inst.install_id)==render(inst.install_id,b,True)
                fr=encode(schema,client,inst.install_id,b,replay=True)
                assert decode(schema,server,fr,authorized_origin=inst.install_id)==render(inst.install_id,b)
                n+=len(b);nb+=1;total+=len(f);strict+=len(fs);replay+=len(fr)
        rows[str(cap)]={'events':n,'batches':nb,'body_B_event':total/n,'with_aliases_B_event':(total+setup)/n,'strict_ids_B_event':strict/n,'conditional_replay_B_event':replay/n,'boundary':'session-aware backlog cap, not real-time flush cadence'}
    out[profile]=rows
(ROOT/'results/confirmation2601.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
