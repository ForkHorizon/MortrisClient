"""Shared paths/workloads. Uses the user's original v4/v3/v2 code from evidence.zip unchanged."""
import sys
from pathlib import Path
EXP=Path('/Users/daliys/Daliys/UnityProjects/MortrisUnity/Assets/MortrisClient/Theory~/transport-v4/06-experiments')
for p in [EXP, EXP.parents[1]/'transport-v3/06-experiments', EXP.parents[1]/'transport-v2/04-experiments']:
    sys.path.insert(0,str(p))
from workloads import make,rebatch,drift
def workload(name,which,cap):
    """which: test101 / val303 / hold909 / train202; cap 0=original uploader cadence."""
    if name=='drift':
        ds={'train202':lambda:drift(202,12,600),'hold909':lambda:drift(808,4,600),'test101':lambda:drift(808,4,600)}[which]()
        return ds  # drift has its own short-session batching
    seed,n={'test101':(101,6),'val303':(303,3),'hold909':(909,6),'train202':(202,18)}[which]
    ds=make(name,seed,n)
    return rebatch(ds,cap) if cap else ds
