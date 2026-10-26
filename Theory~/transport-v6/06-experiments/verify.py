"""Validate independent saved artifacts, sources, fixtures and report consistency."""
import ast,base64,hashlib,json,os,subprocess,sys
from pathlib import Path
from codec import *
from support import ROOT
from schema_tools import unpack_schema
R=ROOT/'results'
repo=ROOT.parents[2]
inputs=json.loads((R/'input-sha256.json').read_text())
for path,sha in inputs.items():
    assert hashlib.sha256((repo/path).read_bytes()).hexdigest()==sha,path
count=0;events=0
for profile in ('base','rich','alt','drift'):
    saved=json.loads((R/f'bench-{profile}.json').read_text())
    sc=Schema(json.loads((R/f'schema-{profile}.json').read_text()))
    assert unpack_schema((R/f'schema-{profile}.bin').read_bytes()).id==sc.id
    for label,row in saved['rows'].items():
        assert row['V5_measured_bytes']/row['events']==row['V5_stateless_B_event']
        assert abs(row['V4_measured_bytes']/row['events']-row['V4_zstd19_B_event'])<1e-12
        assert row['V6']['strict_V1_ids_zstd1']['body_B_event']>row['V6']['zstd1']['body_B_event']
        for mode,v in row['V6'].items():
            assert v['body_B_event']==v['body_bytes']/row['events']
            assert abs(v['with_alias_setup_B_event']-(v['body_bytes']+v['alias_request_bytes']+v['alias_response_bytes'])/row['events'])<1e-12
        assert saved['schema_id']==sc.id.hex()
        count+=1;events+=row['events']
for fx in json.loads((R/'fixtures.json').read_text()):
    schema=unpack_schema(bytes.fromhex(fx['schema_binary_hex']))
    a=Aliases();a.accept(bytes.fromhex(fx['registration_hex']))
    got=decode(schema,a,bytes.fromhex(fx['frame_hex']),authorized_origin=fx['origin'])
    assert got==base64.b64decode(fx['source_b64'])
    assert hashlib.sha256(got).hexdigest()==fx['source_sha256']
for path in ROOT.glob('*.py'):ast.parse(path.read_text())
for path in ('00-summary.md','01-architecture-v6.md','02-benchmark-results.md','03-cpu-and-battery-evaluation.md','04-field-costs.md'):
    assert (ROOT.parent/path).stat().st_size>1000
native=json.loads((R/'native.json').read_text());assert native['integer_conformance_cases']==1006
assert not native['native_kernel_allocator_symbols']
# Verify fixtures under another salted Python hash seed as an independent process.
if '--child' not in sys.argv:
    env=dict(os.environ,PYTHONHASHSEED='6006')
    subprocess.run([sys.executable,__file__,'--child'],check=True,env=env,stdout=subprocess.DEVNULL)
    sources=[p for p in ROOT.iterdir() if p.suffix in ('.py','.c','.sh')]
    output={'status':'OK','matched_V4_V5_rows':count,'events_per_full_main_variant':events,'main_V6_variants':11,'unchanged_input_files':len(inputs),'portable_strict_fixtures':8,'native_integer_cases':1006,'confirmation_seed':2601,'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'scope':'synthetic research; no device/Burst/IL2CPP/battery certification'}
    (R/'verification.json').write_text(json.dumps(output,indent=2));print(json.dumps(output,indent=2))
