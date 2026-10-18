"""Decodes an M7 frame with the Python reference decoder and compares it with the expected events.
Exit code 0 and 'OK <n>' on success. Usage: py_decode.py CATALOG DICTIONARY ALIASES FRAME EXPECTED"""
import importlib.util, json, os, sys
from pathlib import Path
COMPARISON = Path(os.environ['M7_SCRIPTS'])  # Theory~/transport-v7/comparison/scripts
spec = importlib.util.spec_from_file_location('sb', COMPARISON / 'synth_bench.py'); sb = importlib.util.module_from_spec(spec); spec.loader.exec_module(sb)
from transport7 import Catalog, decode  # noqa: E402

catalog_path, dict_path, aliases_path, frame_path, expected_path = sys.argv[1:6]
catalog = Catalog.load(Path(catalog_path).read_bytes())
dictionary = sb.z.ZstdCompressionDict(Path(dict_path).read_bytes()) if Path(dict_path).stat().st_size else None
snapshot = json.loads(Path(aliases_path).read_text())
aliases = sb.Aliases(bytes.fromhex(snapshot['epoch']))
for record in snapshot['records']:
    record = tuple(record); aliases.ids[record] = len(aliases.records); aliases.records.append(record)
expected = json.loads(Path(expected_path).read_text())
origin, events = decode(catalog, aliases, Path(frame_path).read_bytes(), dictionary, authorized_project=expected['project'], authorized_origin=expected['origin'])
want = expected['events']
if len(events) != len(want):
    print('count', len(events), len(want)); sys.exit(1)
keys = ('name', 'sequence', 'ts', 'session_elapsed_ms', 'session_id', 'app_version', 'build_number', 'platform', 'os_version', 'device_class', 'locale', 'timezone_offset_minutes', 'properties')
for i, (got, exp) in enumerate(zip(events, want)):
    for k in keys:
        if got[k] != exp[k]:
            print('mismatch event', i, k, repr(got[k])[:200], repr(exp[k])[:200]); sys.exit(1)
print('OK', len(events))
