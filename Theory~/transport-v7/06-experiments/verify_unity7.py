"""Validate calibrated Unity counters and every raw output against frozen fixtures."""
import hashlib,json,zipfile
from support7 import ROOT

def check(name,source,output):
    report=json.loads(source.read_text())
    assert report['allocation_control_samples']>0
    assert report['empty_control_samples']==0
    assert report['allocation_measurement_valid']
    expected=set(json.loads((ROOT/'results/private/unity-player/Assets/StreamingAssets/manifest.json').read_text())['fixtures'])
    expected_count=12+(4 if (ROOT/'results/native-tables.json').exists()else 0)
    rows=report['measurements'];assert len(rows)==len(expected)==expected_count
    assert {row['fixture']for row in rows}==expected
    for row in rows:
        assert row['gc_alloc_samples']==row['gc_bytes']==0 and row['iterations']==1000 and row['passed'],row['fixture']
        raw=output/(row['fixture']+'.raw');gold=ROOT/'fixtures'/(row['fixture']+'.raw')
        if not gold.exists():gold=ROOT/'results/private'/(row['fixture']+'.raw')
        fixture=json.loads(gold.with_suffix('.json').read_text())
        assert row.get('string_model',False)==fixture.get('string_model',False)
        assert raw.read_bytes()==gold.read_bytes(),row['fixture']
        row.update(raw_parity=True,raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
    report['scope']='Pretyped columns + reused native zstd, excluding ingress/framing/JNI/HTTP. Not a physical-phone or thermal/FPS test.'
    if name.startswith('unity-android'):
        assert report['scripting_backend']=='IL2CPP'and report['development_build']
        assert report['android_abi']=='arm64-v8a'and report['qemu']=='1'and not report['physical_phone']
        apk=ROOT/'results/private/transport-v7-development.apk';assert hashlib.sha256(apk.read_bytes()).hexdigest()==report['apk_sha256']
        native=json.loads((ROOT/'results/android-native-build.json').read_text())
        assert all(a>=16384 for a in native['elf_load_alignments'])
        with zipfile.ZipFile(apk)as z:
            assert 'lib/arm64-v8a/libil2cpp.so'in z.namelist()
            assert hashlib.sha256(z.read('lib/arm64-v8a/libzstd.so')).hexdigest()==native['expected_packaged_plugin_sha256']
    else:assert report['scripting_backend']=='Editor Mono'
    (ROOT/'results'/f'{name}.json').write_text(json.dumps(report,indent=2));return report

def run():
    check('unity-editor',ROOT/'results/private/unity-editor-output/report.json',ROOT/'results/private/unity-editor-output')
    check('unity-android',ROOT/'results/unity-android.json',ROOT/'results/private/unity-android-output')
    if (ROOT/'results/unity-android-16k.json').exists():
        result=check('unity-android-16k',ROOT/'results/unity-android-16k.json',ROOT/'results/private/unity-android-16k-output')
        assert result['page_size']==16384
    print('Unity Editor and available Android IL2CPP sets: calibrated GC and every manifest fixture raw parity per runtime PASS')
if __name__=='__main__':run()
