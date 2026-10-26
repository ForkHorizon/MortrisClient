import hashlib,json
from pathlib import Path
from support7 import ROOT

def run():
    base=Path('/Users/daliys/Daliys/Web/MortrisServer')
    paths=[Path('/Users/daliys/Daliys/UnityProjects/Puzzle/Assets/Scripts/DI/Services/Analytical/PuzzleAnalyticsService.cs'),
           ROOT.parents[2]/'Runtime/Internal/AnalyticsUploader.cs']
    paths += [base/p for p in ('internal/analytics/puzzle_quality_integrity.go','internal/analytics/puzzle_replay.go','internal/facts/build_events.go','dashboard/src/components/pacingMath.ts')]
    result=[]
    for p in paths:
        lines=p.read_text().splitlines()
        hits=[{'line':i,'text':line.strip()}for i,line in enumerate(lines,1) if any(s in line for s in ('placed_state_hash','placed_block_ids','wave_attempt_id','interaction_id','interaction_index','PersistAttempt','FlushPersistedAttempt','CompressionLevel.Fastest'))]
        result.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'hits':hits})
    (ROOT/'results/source-audit.json').write_text(json.dumps(result,indent=2))
if __name__=='__main__':run()
