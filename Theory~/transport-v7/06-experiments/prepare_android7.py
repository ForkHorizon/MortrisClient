"""Use the existing Android toolchain and compile the pinned zstd ARM64 plugin.
All generated research assets stay inside V7; no Editor installation is modified.
"""
import hashlib,json,shutil,struct,subprocess,tarfile,urllib.request
from pathlib import Path
from support7 import ROOT
from prepare_unity7 import PROJECT

EDITOR=Path('/Applications/Unity/Hub/Editor/6000.3.16f1')
ANDROID=EDITOR/'PlaybackEngines/AndroidPlayer'

def module_state():
    before=json.loads((ROOT/'results/unity-module-before.json').read_text())
    assert before['android_supported'],before
    assert (ANDROID/'UnityEditor.Android.Extensions.dll').exists()
    return {'android_supported':True,'module_root':str(ANDROID),'operation':'used existing installed module; no repair/installation performed'}

def run():
    repair=module_state();deps=ROOT/'results/private/android-deps';deps.mkdir(exist_ok=True)
    archive=deps/'zstd-v1.5.7.tar.gz';url='https://codeload.github.com/facebook/zstd/tar.gz/refs/tags/v1.5.7'
    if not archive.exists():
        with urllib.request.urlopen(url,timeout=60)as response:archive.write_bytes(response.read())
    source=deps/'zstd-1.5.7'
    if not source.exists():
        with tarfile.open(archive)as package:package.extractall(deps,filter='data')
    lib=source/'lib';sources=sorted([p for folder in ('common','compress','decompress')for p in (lib/folder).glob('*.c')])
    output=PROJECT/'Assets/Plugins/Android/arm64-v8a/libzstd.so';output.parent.mkdir(parents=True,exist_ok=True)
    clang=ANDROID/'NDK/toolchains/llvm/prebuilt/darwin-x86_64/bin/aarch64-linux-android25-clang'
    command=[str(clang),'-shared','-fPIC','-O2','-DNDEBUG','-DZSTD_LEGACY_SUPPORT=0','-DZSTD_DISABLE_ASM=1','-Wl,-soname,libzstd.so','-Wl,--no-undefined','-Wl,-z,max-page-size=16384','-Wl,-z,common-page-size=16384','-I'+str(lib),'-I'+str(lib/'common'),*[str(p)for p in sources],'-o',str(output)]
    subprocess.run(command,check=True)
    stripped=deps/'stripped-libzstd.so'
    strip=clang.parent/'llvm-strip'
    subprocess.run([str(strip),'--strip-unneeded','-o',str(stripped),str(output)],check=True)
    binary=output.read_bytes();header=struct.unpack_from('<16sHHIQQQIHHHHHH',binary)
    alignments=[struct.unpack_from('<IIQQQQQQ',binary,header[5]+i*header[9])[7] for i in range(header[10]) if struct.unpack_from('<I',binary,header[5]+i*header[9])[0]==1]
    assert alignments and all(a>=16384 for a in alignments),alignments
    shutil.copyfile(source/'LICENSE',PROJECT/'Assets/StreamingAssets/zstd-LICENSE.txt')
    record={'module_discovery':repair,'source_url':url,'source_archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
            'zstd':'1.5.7','ABI':'arm64-v8a','minimum_api':25,'compiler':subprocess.check_output([str(clang),'--version'],text=True),
            'command':command,'plugin_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'plugin_bytes':output.stat().st_size,'expected_packaged_plugin_sha256':hashlib.sha256(stripped.read_bytes()).hexdigest(),'packaging_transform':'NDK llvm-strip --strip-unneeded','elf_load_alignments':alignments}
    (ROOT/'results/android-native-build.json').write_text(json.dumps(record,indent=2));print('Built',output,flush=True)
if __name__=='__main__':run()
