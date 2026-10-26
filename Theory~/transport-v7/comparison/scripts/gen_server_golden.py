"""Writes synthetic golden V7 packets (made by the Python reference encoder) for the Go server decoder tests.
Usage: gen_server_golden.py OUT_DIR   (synthetic data only: no Puzzle data, safe to commit)."""
import importlib.util, json, sys, uuid
from pathlib import Path
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('sb', HERE / 'synth_bench.py'); sb = importlib.util.module_from_spec(spec); spec.loader.exec_module(sb)
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)

def v4(u):  # the server's wire validators accept only version-4-shaped identifiers
    n = uuid.UUID(u).int
    n = (n & ~(0xf << 76)) | (4 << 76)
    n = (n & ~(0x3 << 62)) | (0x2 << 62)
    return str(uuid.UUID(int=n))

def fix(ds):
    for inst, bs in ds:
        inst.install_id = v4(inst.install_id)
        for b in bs:
            for e in b:
                e['session_id'] = v4(e['session_id']); e['event_id'] = v4(e['event_id'])
    return ds
train = sb.rebatch(fix(sb.corpus('high', 11, 20, 300, (15, 60))), 100)
c = sb.Catalog.train(sb.PROJECT, train)
d = sb.z.train_dictionary(16384, sb.samples(c, train), level=1)
inst, bs = fix(sb.corpus('high', 33, 1, 100, (15, 60)))[0]; batch = sb.rebatch([(inst, bs)], 100)[0][1][0]
a = sb.Aliases(bytes(8)); a.register(inst.install_id, batch)
(out / 'catalog.json').write_bytes(c.data)
(out / 'aliases.json').write_text(json.dumps({'epoch': a.epoch.hex(), 'records': a.records}, ensure_ascii=True, separators=(',', ':')))
(out / 'dictionary.bin').write_bytes(d.as_bytes())
(out / 'packet-sequence.bin').write_bytes(sb.encode(c, a, inst.install_id, batch, d, False))
(out / 'packet-legacy-ids.bin').write_bytes(sb.encode(c, a, inst.install_id, batch, d, True))
(out / 'packet-nodict.bin').write_bytes(sb.encode(c, a, inst.install_id, batch, None, False)) if False else None
exp = [dict(name=e['name'], sequence=e['sequence'], ts_ms=e['ts'], session_elapsed_ms=e['session_elapsed_ms'], session_id=e['session_id'], event_id=e['event_id'],
            app_version=e['app_version'], build_number=e['build_number'], platform=e['platform'], os_version=e['os_version'], device_class=e['device_class'],
            locale=e['locale'], timezone_offset_minutes=e['timezone_offset_minutes'], properties=e['properties']) for e in batch]
(out / 'expected.json').write_text(json.dumps(dict(project=sb.PROJECT, origin=inst.install_id, events=exp), ensure_ascii=True))
print('events', len(exp), 'project', sb.PROJECT, 'origin', inst.install_id)
