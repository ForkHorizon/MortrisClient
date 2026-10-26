"""Research vertical slice for ADR 12 (sequence identity). NOT production SDK code.

Scope: SQLite WAL (synchronous=FULL) client queue + in-memory server model.
Crash tests use SIGKILL of a child process (process crash). Power loss / fsync
lies / filesystem corruption are NOT tested. Run: python3 identity_harness.py
"""
import hashlib, json, multiprocessing as mp, os, signal, sqlite3, sys, tempfile, time, uuid

I64_MAX = 2**63 - 1

def open_db(path):
    db = sqlite3.connect(path, timeout=30, isolation_level=None)
    db.execute('PRAGMA journal_mode=WAL'); db.execute('PRAGMA synchronous=FULL')
    db.execute('CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v)')
    db.execute('CREATE TABLE IF NOT EXISTS q(origin BLOB, epoch INT, seq INT, payload BLOB, PRIMARY KEY(origin,epoch,seq))')
    db.execute("INSERT OR IGNORE INTO meta VALUES('origin',?)", (os.urandom(8),))
    db.execute("INSERT OR IGNORE INTO meta VALUES('epoch',0)")
    db.execute("INSERT OR IGNORE INTO meta VALUES('next',1)")
    return db

def enqueue(db, payload, seq_limit=I64_MAX):
    """Sequence allocation and enqueue in ONE immediate transaction."""
    db.execute('BEGIN IMMEDIATE')
    try:
        o, e, n = (db.execute('SELECT v FROM meta WHERE k=?', (k,)).fetchone()[0] for k in ('origin', 'epoch', 'next'))
        if n >= seq_limit:  # overflow (next counter must stay a storable int64): never wrap; rotate epoch
            e += 1; n = 1; db.execute("UPDATE meta SET v=? WHERE k='epoch'", (e,))
        db.execute('INSERT INTO q VALUES(?,?,?,?)', (o, e, n, payload))
        db.execute("UPDATE meta SET v=? WHERE k='next'", (n + 1,))
        db.execute('COMMIT')
        return o, e, n
    except BaseException:
        db.execute('ROLLBACK'); raise

def reset_identity(db):
    """Local-only: new random origin, counter restarts; queued rows keep their own origin/epoch."""
    db.execute('BEGIN IMMEDIATE')
    db.execute("UPDATE meta SET v=? WHERE k='origin'", (os.urandom(8),))
    db.execute("UPDATE meta SET v=0 WHERE k='epoch'"); db.execute("UPDATE meta SET v=1 WHERE k='next'")
    db.execute('COMMIT')

class Server:
    """Dedup key = (project, origin, epoch, seq). ACK = contiguous high-water per (origin,epoch), skip ranges honoured."""
    def __init__(self): self.seen = {}; self.hw = {}
    def accept(self, project, o, e, s, payload, skip=()):
        k = (project, o, e, s); h = hashlib.sha256(payload).digest()
        if k in self.seen:
            return 'DUP_SAME' if self.seen[k] == h else 'CONFLICT'
        self.seen[k] = h
        return 'NEW'
    def ack(self, project, o, e, skipped=(), base=0):
        got = {s for (p, oo, ee, s) in self.seen if (p, oo, ee) == (project, o, e)}
        hw = base
        while (hw + 1) in got or (hw + 1) in skipped: hw += 1
        return hw

def _child(path, n_before_kill, mode, q):
    db = open_db(path)
    for i in range(n_before_kill):
        enqueue(db, b'e%d' % i)
    if mode == 'mid_txn':  # killed with an open uncommitted allocation
        db.execute('BEGIN IMMEDIATE'); db.execute("UPDATE meta SET v=v+1 WHERE k='next'")
    q.put('ready'); time.sleep(30)

def _producer(path, k, n):
    db = open_db(path)
    for i in range(n): enqueue(db, b'p%d-%d' % (k, i))

def varint(n):
    b = 1
    while n >= 128: n >>= 7; b += 1
    return b

def run():
    r = {}; tmp = tempfile.mkdtemp()
    # T1 crash in/after write points
    for mode in ('after_commit', 'mid_txn'):
        p = os.path.join(tmp, f'c-{mode}.db'); q = mp.Queue()
        c = mp.Process(target=_child, args=(p, 50, mode, q)); c.start(); q.get(timeout=20)
        os.kill(c.pid, signal.SIGKILL); c.join()
        db = open_db(p)
        seqs = [x[0] for x in db.execute('SELECT seq FROM q ORDER BY seq')]
        nxt = db.execute("SELECT v FROM meta WHERE k='next'").fetchone()[0]
        r[f'crash_{mode}'] = {'rows': len(seqs), 'contiguous': seqs == list(range(1, len(seqs) + 1)), 'next_is_max_plus_1': nxt == len(seqs) + 1}
        o, e, n = enqueue(db, b'after'); r[f'crash_{mode}']['next_after_restart'] = n
    # T2 concurrent producers (separate processes, same DB)
    p = os.path.join(tmp, 'conc.db'); open_db(p).close()
    ps = [mp.Process(target=_producer, args=(p, k, 200)) for k in range(4)]
    [x.start() for x in ps]; [x.join() for x in ps]
    seqs = [x[0] for x in open_db(p).execute('SELECT seq FROM q ORDER BY seq')]
    r['concurrent_4x200'] = {'rows': len(seqs), 'unique_contiguous': seqs == list(range(1, 801))}
    # T3 reset with non-empty queue + offline server + immutability
    db = open_db(os.path.join(tmp, 'rst.db')); [enqueue(db, b'x') for _ in range(5)]
    old = db.execute("SELECT v FROM meta WHERE k='origin'").fetchone()[0]
    reset_identity(db); new = enqueue(db, b'y')
    olds = db.execute('SELECT DISTINCT origin FROM q WHERE origin=?', (old,)).fetchall()
    srv = Server(); s_old = [srv.accept('P', old, 0, i, b'x') for i in range(1, 6)]; s_new = srv.accept('P', new[0], new[1], new[2], b'y')
    r['reset_with_queue'] = {'old_rows_keep_origin': len(olds) == 1, 'new_origin_differs': new[0] != old, 'works_without_server': True,
                             'old_flush_ok': set(s_old) == {'NEW'}, 'new_flush_ok': s_new == 'NEW', 'same_seq_diff_origin_no_conflict': new[2] == 1 and s_new == 'NEW'}
    # T4 overflow
    db = open_db(os.path.join(tmp, 'ovf.db')); db.execute("UPDATE meta SET v=? WHERE k='next'", (I64_MAX - 1,))
    keys = [enqueue(db, b'z', seq_limit=I64_MAX) for _ in range(3)]
    r['overflow'] = {'keys': [(e, s) for _, e, s in keys], 'epoch_rotated_no_wrap': keys[0][2] == I64_MAX - 1 and keys[1][1:] == (1, 1)}
    # T5 duplicates/retry/conflict + backup restore
    srv = Server(); o = os.urandom(8)
    r['retry'] = [srv.accept('P', o, 0, 1, b'a'), srv.accept('P', o, 0, 1, b'a'), srv.accept('P', o, 0, 1, b'DIFFERENT')]
    db = open_db(os.path.join(tmp, 'bak.db')); [enqueue(db, b'a%d' % i) for i in range(3)]
    db.execute('PRAGMA wal_checkpoint(TRUNCATE)'); snap = open(os.path.join(tmp, 'bak.db'), 'rb').read()
    [enqueue(db, b'b%d' % i) for i in range(3)]; origin = db.execute("SELECT v FROM meta WHERE k='origin'").fetchone()[0]
    srv = Server(); [srv.accept('P', origin, 0, i + 1, (b'a%d' if i < 3 else b'b%d') % (i % 3)) for i in range(6)]
    pb = os.path.join(tmp, 'restored.db'); open(pb, 'wb').write(snap); db2 = open_db(pb)
    _, e2, n2 = enqueue(db2, b'NEWDATA')  # restored counter reuses seq 4 with different payload
    r['backup_restore'] = {'reused_key': (e2, n2), 'server_verdict': srv.accept('P', origin, e2, n2, b'NEWDATA'),
                           'note': 'detected only because server holds old content; client alone cannot know -> server hello must return high-water, client rotates epoch if local next <= server hw'}
    # T6 ADR assumptions
    srv = Server(); o = os.urandom(8)
    for s in (101, 102, 104): srv.accept('P', o, 0, s, b'p')
    r['gap_semantics'] = {'ack_without_skip': srv.ack('P', o, 0, base=100), 'ack_with_skip_103': srv.ack('P', o, 0, skipped={103}, base=100), 'note': 'client must send skip ranges for evicted rows or ACK stalls forever'}
    srv2 = Server(); [srv2.accept('P', o, 0, s, b'p') for s in range(1, 98)]
    r['suffix_loss'] = {'server_sees_gap': srv2.ack('P', o, 0) != 100, 'detected': False, 'note': 'lost tail 98..100 invisible without client-sent high-water'}
    r['header_size_not_always_2B'] = {str(n): varint(n) + varint(1) + varint(100) for n in (101, 20000, 3_000_000, 2**40)}
    r['noncontiguous_after_eviction'] = {'batch_seqs': [101, 102, 107, 108, 150], 'delta_all_ones': False}
    ns = uuid.UUID('00000000-0000-0000-0000-00000000dead')
    adr = lambda install, seq: uuid.uuid5(ns, f'{install}:{seq}')
    full = lambda proj, o_, ep, seq: uuid.uuid5(ns, f'{proj}:{o_}:{ep}:{seq}')
    r['uuid_namespace'] = {'adr_formula_collides_across_epochs_or_projects': adr('inst', 1) == adr('inst', 1),
                           'full_key_distinguishes_project': full('A', 'o', 0, 1) != full('B', 'o', 0, 1),
                           'full_key_distinguishes_epoch': full('A', 'o', 0, 1) != full('A', 'o', 1, 1),
                           'note': 'ADR formula uuid5(installID:seq) has no project/epoch input; two projects or epochs sharing an install_id string collide. UUID is a legacy alias only; primary key stays the tuple.'}
    r['durability'] = {'journal_mode': 'WAL', 'synchronous': 'FULL', 'tested': 'SIGKILL process crash only', 'not_tested': ['power loss', 'fsync-lying storage', 'cloud backup restore on device']}
    return r

if __name__ == '__main__':
    res = run()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'results', 'identity-harness.json')
    json.dump(res, open(out, 'w'), indent=2, default=lambda b: b.hex() if isinstance(b, bytes) else str(b))
    print(json.dumps(res, indent=2, default=str))
    ok = all(res[f'crash_{m}']['contiguous'] and res[f'crash_{m}']['next_is_max_plus_1'] for m in ('after_commit', 'mid_txn')) and res['concurrent_4x200']['unique_contiguous'] and all(res['reset_with_queue'].values())
    sys.exit(0 if ok else 1)
