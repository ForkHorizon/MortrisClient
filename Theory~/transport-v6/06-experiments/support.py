"""Read-only imports of the frozen V5/V4/V3/V2 research inputs."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
V5 = ROOT.parents[1] / 'transport-v5/06-experiments'
sys.path.insert(0, str(V5))
# V5's support has this same module name, so reproduce only its path setup.
sys.path.insert(0, str(ROOT.parents[1] / 'transport-v4/06-experiments'))
import core, wire, exact
from workloads import make, rebatch, drift
from primitives import Reader, u, zz, packbits, readbits
