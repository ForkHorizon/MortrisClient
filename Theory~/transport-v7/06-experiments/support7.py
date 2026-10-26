"""Read-only reuse of frozen V6 neutral value/alias primitives and workloads."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
V6 = ROOT.parents[1] / 'transport-v6/06-experiments'
sys.path.insert(0, str(V6))
import codec as v6
from support import core, wire, Reader, u, make, rebatch, drift
import zstandard as z


def canonical_source(origin, events, preserve_ids=False):
    """JSON object order is not a semantic field; all values/lexemes stay exact."""
    ordered = [dict(e, properties=dict(sorted(e['properties'].items()))) for e in events]
    return v6.render(origin, ordered, preserve_ids)


def project_source(project, origin, events, preserve_ids=False):
    import json
    source = v6.render(origin, events, preserve_ids)
    old = b'"project_id":' + json.dumps(wire.PROJECT_ID).encode()
    new = b'"project_id":' + json.dumps(project).encode()
    return source.replace(old, new, 1)
