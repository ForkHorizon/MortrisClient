"""Protect prior research/product inputs without committing tool state."""
import hashlib, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]

def inputs():
    roots = [REPO / 'Runtime', *(REPO / f'transport-v{n}' for n in ())]
    roots += [REPO / f'Theory~/transport-v{n}' for n in range(2, 7)]
    paths = [p for root in roots for p in root.rglob('*') if p.is_file() and not any(x in p.parts for x in ('.venv', '__pycache__'))]
    paths += [Path('/Users/daliys/Daliys/UnityProjects/Puzzle/Assets/Scripts/DI/Services/Analytical/PuzzleAnalyticsService.cs')]
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}

if __name__ == '__main__':
    target = ROOT / 'results/protected-inputs.json'
    if target.exists():
        assert json.loads(target.read_text()) == inputs(), 'protected inputs changed'
        print('Protected input SHA256 verified')
    else:
        target.write_text(json.dumps(inputs(), indent=2))
