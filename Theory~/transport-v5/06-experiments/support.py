import sys
from pathlib import Path
EXP=Path(__file__).resolve().parents[2]/'transport-v4/06-experiments'
sys.path.insert(0,str(EXP))
import core,wire,exact
from workloads import make,rebatch,drift
from primitives import Reader,u
