"""Runs the SDK x corpus x repeat matrix on the emulator. Order is a seeded shuffle of blocks (each block holds every cell once).
Usage: run_matrix.py REPEATS SHARD NSHARDS ADB_SERIAL COLLECTOR_PORT   (emulator with DNS guard must be running; see README in report)"""
import json, os, random, subprocess, sys, time
from pathlib import Path
H = Path(__file__).resolve().parent; OUT = H.parent / 'results' / os.environ.get('OUTDIR', 'sdk-runs'); REPLAY = Path(os.environ.get('REPLAY_DIR', H / 'replay')); CORPORA = os.environ.get('CORPORA', 'low,high').split(','); OUT.mkdir(parents=True, exist_ok=True)
SHARD, NSH, SERIAL, PORT = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], int(sys.argv[5])
ADB = os.path.expanduser('~/Library/Android/sdk/platform-tools/adb'); HZ = 10; N = 600; TAIL = 45
PY = sys.executable
MODES = {'base_parse': ['--es', 'sdk', 'none_parse'], 'base_map': ['--es', 'sdk', 'none_map'],
         'amplitude_default': ['--es', 'sdk', 'amplitude'],
         'amplitude_b100': ['--es', 'sdk', 'amplitude', '--ei', 'amp_threshold', '100', '--ei', 'amp_batch', '100'],
         'ga_default': ['--es', 'sdk', 'ga']}
def sh(*a, **k): return subprocess.run((a[0], '-s', SERIAL) + a[1:], capture_output=True, text=True, **k).stdout
SEL = os.environ.get('MODES'); cells = [(m, c) for m in MODES if not SEL or m in SEL.split(',') for c in CORPORA]
rng = random.Random(20261017); plan = []
for rep in range(int(sys.argv[1])):
    b = cells[:]; rng.shuffle(b); plan += [(rep,) + x for x in b]
for i, (rep, mode, corpus) in enumerate(plan):
    if i % NSH != SHARD: continue
    rid = f'{mode}-{corpus}-r{rep}'; f = OUT / f'{rid}.jsonl'
    if f.exists() and f.stat().st_size > 0: continue
    col = subprocess.Popen([PY, str(H / 'collector.py'), str(PORT), str(f)]); time.sleep(1.5)
    sh(ADB, 'shell', 'am', 'force-stop', 'bench.sdk'); sh(ADB, 'shell', 'pm', 'clear', 'bench.sdk')
    sh(ADB, 'shell', 'mkdir', '-p', '/sdcard/Android/data/bench.sdk/files'); sh(ADB, 'push', str(REPLAY / f'{corpus}.jsonl'), '/sdcard/Android/data/bench.sdk/files/replay.jsonl')
    sh(ADB, 'logcat', '-c'); t0 = time.time()
    sh(ADB, 'shell', 'am', 'start', '-n', 'bench.sdk/bench.Main', *MODES[mode], '--es', 'host', f'10.0.2.2:{PORT}', '--ei', 'hz', str(HZ), '--ei', 'tail', str(TAIL), '--ei', 'n', str(N))
    time.sleep(6 + N / HZ + TAIL + 8)
    log = [l for l in sh(ADB, 'logcat', '-d', '-s', 'BENCH').splitlines() if 'BENCH' in l]
    col.terminate(); col.wait()
    (OUT / f'{rid}.logcat.txt').write_text('\n'.join(log)); print(rid, round(time.time() - t0), flush=True)
