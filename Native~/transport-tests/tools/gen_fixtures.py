"""Generates synthetic fixtures for the C# V7 encoder tests with the Python reference implementation.
Usage (research virtualenv): PYTHONDONTWRITEBYTECODE=1 python gen_fixtures.py ../fixtures
Everything is synthetic; no Puzzle data. Outputs, per catalog variant ('plain' and 'logical' strings):
  catalog-<v>.json, dictionary-<v>.bin, batch-<profile>.json (SDK queue payloads), expected-<profile>.json, classify.json.
"""
import importlib.util, json, sys, uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPARISON = HERE.parents[2] / 'Theory~/transport-v7/comparison/scripts'
spec = importlib.util.spec_from_file_location('sb', COMPARISON / 'synth_bench.py'); sb = importlib.util.module_from_spec(spec); spec.loader.exec_module(sb)
from support7 import core  # noqa: E402  (added to sys.path by synth_bench)

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)

def v4(u):
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

def iso(ms): return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (ms % 1000)

import random
def widen(ds, seed):
    # A 900-character incompressible note per event: a 100-event batch no longer fits the encoder's initial raw buffer.
    rng = random.Random(seed)
    for inst, bs in ds:
        for b in bs:
            for e in b:
                e['name'] = 'wide_' + e['name']
                e['properties']['note'] = ''.join(rng.choice('abcdefghijklmnopqrstuvwxyz0123456789 ') for _ in range(900))
    return ds

train = []
for profile in ('low', 'high'):
    train += fix(sb.corpus(profile, 11, 20, 300, (15, 60)))
train += widen(fix(sb.corpus('low', 12, 4, 300, (15, 60))), 99)
train_ds = sb.rebatch(train, 100)

def sdk_event(e):
    return {'event_id': e['event_id'], 'session_id': e['session_id'], 'name': e['name'], 'occurred_at_client': iso(e['ts']),
            'session_elapsed_ms': e['session_elapsed_ms'], 'app_version': e['app_version'], 'build_number': e['build_number'],
            'platform': e['platform'], 'os_version': e['os_version'], 'device_class': e['device_class'], 'locale': e['locale'],
            'timezone_offset_minutes': e['timezone_offset_minutes'], 'properties': e['properties'], 'sequence': e['sequence']}

summary = {}
for variant, logical in (('plain', False), ('logical', True)):
    catalog = sb.Catalog.train(sb.PROJECT, train_ds, logical)
    samples = []
    for inst, bs in train_ds:
        a = sb.Aliases(bytes(8))
        for b in bs:
            a.register(inst.install_id, b); samples.append(sb.raw_encode(catalog, a, inst.install_id, b, False, True, True))
    dictionary = sb.z.train_dictionary(16384, samples, level=1)
    (out / f'catalog-{variant}.json').write_bytes(catalog.data)
    (out / f'dictionary-{variant}.bin').write_bytes(dictionary.as_bytes())
    summary[variant] = {'catalog_id': catalog.id.hex(), 'shapes': len(catalog.shapes)}

for profile in ('low', 'high', 'wide'):
    ds = fix(sb.corpus('low' if profile == 'wide' else profile, 33, 1, 100, (3, 9)))
    if profile == 'wide': ds = widen(ds, 7)
    inst, bs = ds[0]
    batch = sb.rebatch([(inst, bs)], 100)[0][1][0]
    (out / f'batch-{profile}.json').write_text(json.dumps([sdk_event(e) for e in batch], ensure_ascii=True, separators=(',', ':')))
    (out / f'expected-{profile}.json').write_text(json.dumps({'project': sb.PROJECT, 'origin': inst.install_id, 'events': [
        {k: e[k] for k in ('name', 'sequence', 'ts', 'session_elapsed_ms', 'session_id', 'app_version', 'build_number', 'platform', 'os_version', 'device_class', 'locale', 'timezone_offset_minutes', 'properties')} for e in batch]}, ensure_ascii=True))

# Classification vectors: JSON text -> expected V7 type per the Python reference (core._vtype of json.loads).
lexemes = ['0', '-0', '1', '-1', '9223372036854775807', '-9223372036854775808', '9223372036854775808', '18446744073709551615', '1.0', '-0.0', '0.5', '0.1', '3.14',
           '1e3', '1E+20', '1.5e-7', '123456789.123456789', '16777216', '16777217', '16777216.0', '0.000001', '340282346638528859811704183484516925440.0', '1e39', '4.9e-324']
strings = ['', 'a', 'hello world', '0123456789abcdef', '0123456789abcdeF', '0123456789abcde', '0123456789abcdef0', 'e40c2fc4-e158-4b57-a6e0-4b647a9d9691',
           'E40C2FC4-E158-4B57-A6E0-4B647A9D9691', 'e40c2fc4-e158-4b57-a6e0-4b647a9d969', 'f' * 64, '光', 'x' * 100]
vectors = [{'json': lx, 'type': core._vtype(json.loads(lx))} for lx in lexemes]
vectors += [{'json': json.dumps(s), 'type': core._vtype(json.loads(json.dumps(s)))} for s in strings]
vectors += [{'json': 'true', 'type': core._vtype(True)}, {'json': 'false', 'type': core._vtype(False)}, {'json': 'null', 'type': core._vtype(None)}]
(out / 'classify.json').write_text(json.dumps(vectors, indent=1))
(out / 'summary.json').write_text(json.dumps(summary, indent=1)); print(summary)
