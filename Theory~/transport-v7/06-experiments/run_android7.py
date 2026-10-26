"""Run only the isolated research APK on the named AVD; no Puzzle launch or data changes."""
import hashlib,json,subprocess,time
from pathlib import Path
from support7 import ROOT

ADB='/Users/daliys/Library/Android/sdk/platform-tools/adb'
SERIAL='emulator-5556';AVD='Mortris_API_35';NAME='unity-android';PACKAGE='com.daliys.transport7.research'

def adb(*args,check=True):
    return subprocess.run([ADB,'-s',SERIAL,*args],capture_output=True,text=True,check=check)

def run():
    devices=subprocess.check_output([ADB,'devices'],text=True)
    started=False
    if SERIAL not in devices:
        log=(ROOT/'results'/(NAME+'-emulator.log')).open('w')
        proc=subprocess.Popen(['/Users/daliys/Library/Android/sdk/emulator/emulator','-avd',AVD,'-port',SERIAL.split('-')[-1],'-no-window','-no-boot-anim'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        (ROOT/'results/private'/(NAME+'-emulator-pid.txt')).write_text(str(proc.pid));started=True
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        boot=adb('shell','getprop','sys.boot_completed',check=False)
        if boot.returncode==0 and boot.stdout.strip()=='1':break
        time.sleep(1)
    else:raise RuntimeError('emulator boot timeout')
    apk=ROOT/'results/private/transport-v7-development.apk'
    adb('install','-r',str(apk))
    component=adb('shell','cmd','package','resolve-activity','--brief',PACKAGE).stdout.strip().splitlines()[-1]
    assert component.startswith(PACKAGE+'/'),component
    adb('shell','am','force-stop',PACKAGE)
    adb('shell','run-as',PACKAGE,'rm','-rf','files/benchmark-output')
    adb('shell','am','start','-n',component)
    device='files/benchmark-output'
    report=None;deadline=time.monotonic()+180;seen_pid=False;missing_polls=0
    while time.monotonic()<deadline:
        response=adb('exec-out','run-as',PACKAGE,'cat',device+'/report.json',check=False)
        if response.returncode==0:
            try:report=json.loads(response.stdout);break
            except json.JSONDecodeError:pass
        running=bool(adb('shell','pidof',PACKAGE,check=False).stdout.strip())
        if running:seen_pid=True;missing_polls=0
        elif seen_pid:missing_polls+=1
        if seen_pid and missing_polls>=3:break
        time.sleep(1)
    logs=adb('logcat','-d','-v','brief','-s','Unity','AndroidRuntime').stdout
    (ROOT/'results/private'/(NAME+'-logcat.txt')).write_text(logs)
    if report is None:raise RuntimeError('Android app exited or report timed out; inspect private/'+NAME+'-logcat.txt')
    output=ROOT/'results/private'/(NAME+'-output');output.mkdir(exist_ok=True)
    for row in report['measurements']:
        label=row['fixture'];target=output/(label+'.raw')
        result=subprocess.run([ADB,'-s',SERIAL,'exec-out','run-as',PACKAGE,'cat',device+'/'+label+'.raw'],capture_output=True,check=True)
        target.write_bytes(result.stdout)
        expected=ROOT/'fixtures'/(label+'.raw')
        if not expected.exists():expected=ROOT/'results/private'/(label+'.raw')
        assert target.read_bytes()==expected.read_bytes(),label
        row['raw_parity']=True
    report.update(apk_sha256=hashlib.sha256(apk.read_bytes()).hexdigest(),device_serial=SERIAL,
                  android_release=adb('shell','getprop','ro.build.version.release').stdout.strip(),
                  android_abi=adb('shell','getprop','ro.product.cpu.abi').stdout.strip(),
                  qemu=adb('shell','getprop','ro.kernel.qemu').stdout.strip(),page_size=int(adb('shell','getconf','PAGESIZE').stdout.strip()),started_emulator=started)
    (ROOT/'results'/(NAME+'.json')).write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':
    import argparse,re
    parser=argparse.ArgumentParser();parser.add_argument('--serial',default=SERIAL);parser.add_argument('--avd',default=AVD);parser.add_argument('--name',default=NAME)
    args=parser.parse_args();assert re.fullmatch(r'unity-android(?:-16k)?',args.name)
    SERIAL,AVD,NAME=args.serial,args.avd,args.name;run()

