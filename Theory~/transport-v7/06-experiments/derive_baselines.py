"""Add matched legacy-ID gzip baselines without retraining or rerunning codecs."""
import gzip,json
from support7 import ROOT,v6,project_source
from bench7 import dataset
from game_cleanup import cleaned
from real_data import load

def update(path, datasets, project=None):
    obj=json.loads(path.read_text())
    for row,ds in zip(obj['rows'],datasets):
        n=sum(len(b)for _,bs in ds for b in bs);assert n==row['events']
        total=sum(len(gzip.compress(project_source(project,i.install_id,b,False) if project else v6.render(i.install_id,b,False),1,mtime=0))for i,bs in ds for b in bs)
        row['bytes']['v1_gzip1_legacy_ids']=total;row['B_event']['v1_gzip1_legacy_ids']=total/n
    path.write_text(json.dumps(obj,indent=2))

def run():
    for profile in ('base','rich','alt','drift'):
        datasets=[]
        for seed in (101,1729,2601):
            ds=dataset(profile,seed,6);datasets.extend((ds,cleaned(ds,migrate_interactions=True)))
        update(ROOT/'results'/f'bench-{profile}.json',datasets)
    _,test=load();update(ROOT/'results/bench-real.json',[test,cleaned(test),cleaned(test,migrate_interactions=True)],project='puzzle_gravity_test')
if __name__=='__main__':run()
