"""Runs SDK cells on one emulator with the real-event replay. Usage: run_android.py SERIAL PORT LABEL REPS N TAIL mode[,mode...]
Modes: base_map ga_default amplitude_default amplitude_b100 firebase hyperkit_core hyperkit_ctx. Output: results/android/<label>/<mode>-r<rep>.{logcat.txt,col.jsonl}
Each run: fresh app data, collector counting bytes at the socket (cleartext), guest-side calibration spins logged by the app."""
import os, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent; H = ROOT.parent / 'Theory~/transport-v7/comparison/harness'
ADB = os.path.expanduser('~/Library/Android/sdk/platform-tools/adb')
serial, port, label, reps, n, tail, modes = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), sys.argv[7].split(',')
OUT = ROOT / 'results/android' / label; OUT.mkdir(parents=True, exist_ok=True)
REPLAY = ROOT / 'work/replay_real_20k.jsonl'
TAILS = {'amplitude_default': 300, 'amplitude_b100': 150, 'ga_default': 120, 'firebase': 90, 'hyperkit_core': 30, 'hyperkit_ctx': 30, 'base_map': 20, 'adjust': 120, 'facebook': 90}
EX = {'base_map': ['--es', 'sdk', 'none_map'], 'ga_default': ['--es', 'sdk', 'ga'], 'amplitude_default': ['--es', 'sdk', 'amplitude'],
      'amplitude_b100': ['--es', 'sdk', 'amplitude', '--ei', 'amp_threshold', '100', '--ei', 'amp_batch', '100'], 'firebase': ['--es', 'sdk', 'firebase'],
      'hyperkit_core': ['--es', 'sdk', 'hyperkit_core'], 'hyperkit_ctx': ['--es', 'sdk', 'hyperkit_ctx'], 'adjust': ['--es', 'sdk', 'adjust'], 'facebook': ['--es', 'sdk', 'facebook']}
def gms_ticks():
    # CPU ticks (utime+stime, 10 ms) of Google Play services processes: Firebase Analytics runs its measurement service there, not in the app process
    out = sh('shell', 'for n in com.google.android.gms com.google.android.gms.persistent com.google.android.gms.unstable; do for p in $(pidof $n); do echo $n $(cut -d" " -f14,15 /proc/$p/stat); done; done')
    t = {}
    for l in out.splitlines():
        f = l.split()
        if len(f) == 3: t[f[0]] = int(f[1]) + int(f[2])
    return t
def sh(*a, timeout=120): return subprocess.run((ADB, '-s', serial) + a, capture_output=True, text=True, timeout=timeout).stdout
HOSTADDR = os.environ.get('HOSTADDR', '10.0.2.2')
if HOSTADDR != '10.0.2.2': sh('reverse', f'tcp:{port}', f'tcp:{port}')
else:
    sh('root'); time.sleep(2)
for rep in range(reps):
    for mode in modes:
        rid = f'{mode}-r{rep}'; log = OUT / f'{rid}.logcat.txt'
        if log.exists() and 'perf2' in log.read_text(): continue
        col = subprocess.Popen([sys.executable, str(H / 'collector.py'), str(port), str(OUT / f'{rid}.col.jsonl')]); time.sleep(1.5)
        sh('shell', 'am', 'force-stop', 'bench.sdk'); sh('shell', 'pm', 'clear', 'bench.sdk')
        sh('shell', 'mkdir', '-p', '/sdcard/Android/data/bench.sdk/files'); sh('push', str(REPLAY), '/sdcard/Android/data/bench.sdk/files/replay.jsonl', timeout=300)
        if mode == 'firebase': sh('shell', 'setprop', 'debug.firebase.analytics.app', '.none.')  # production mode: debug mode uploads every event separately and inflates CPU
        g0 = gms_ticks(); sh('logcat', '-c'); t0 = time.time(); load = os.getloadavg()[0]
        sh('shell', 'am', 'start', '-n', 'bench.sdk/bench.Main', *EX[mode], '--es', 'host', f'{HOSTADDR}:{port}', '--ei', 'hz', os.environ.get('HZ', '0'), '--ei', 'marker', os.environ.get('MARKER', '0'), '--ei', 'tail', str(TAILS[mode] if tail == 0 else tail), '--ei', 'n', str(n))
        done = False
        for _ in range(int((n / 20 + (TAILS[mode] if tail == 0 else tail) + 400) / 3)):
            time.sleep(3); text = sh('logcat', '-d', '-s', 'BENCH')
            if 'tail_done' in text or 'FAIL' in text: done = True; break
        g1 = gms_ticks(); du = sh('shell', 'du -sk /data/data/bench.sdk/databases /data/data/bench.sdk/files /data/data/bench.sdk/cache /data/data/bench.sdk/shared_prefs 2>/dev/null; du -sk /data/data/com.google.android.gms/databases/google_app_measurement.db 2>/dev/null').replace('\n', ';'); text = sh('logcat', '-d', '-s', 'BENCH', 'AndroidRuntime:E')
        log.write_text(f'host_load_at_start={load:.2f}\nhost_load_at_end={os.getloadavg()[0]:.2f}\ngms_cpu_ticks_delta=' + str({k: g1.get(k, 0) - g0.get(k, 0) for k in g1}) + '\n' + '\n'.join(l for l in text.splitlines()))
        col.terminate(); col.wait(); print(rid, 'done' if done else 'TIMEOUT', round(time.time() - t0), flush=True)
