#!/usr/bin/env python3
"""Real Puzzle corpus -> replay files for the comparison, split BY INSTALL (sha256(install)%5==0 -> train, the rest -> holdout; the same rule that trained the V7 catalog/dictionary).
Outputs in data/: puzzle_slice_NN.jsonl (holdout, one install's 3000 consecutive events, NN=00..19), puzzle_hold_100k.jsonl (holdout windows from many installs),
puzzle_train_20k.jsonl (train installs, used only to warm the servers), split_report.json (install lists, hashes, overlap check)."""
import gzip, hashlib, json, random, sys
from collections import defaultdict
SRC = '../night-run~/work/puzzle-1m.jsonl.gz'; random.seed(20261026)
by = defaultdict(list)
for line in gzip.open(SRC, 'rt'):
    e = json.loads(line.rstrip('\n').replace('\\\\', '\\'))
    by[e['install_id']].append((e['sequence'], e['name'], e['properties']))
def is_train(i): return int(hashlib.sha256(i.encode()).hexdigest(), 16) % 5 == 0
train = sorted(i for i in by if is_train(i)); hold = sorted(i for i in by if not is_train(i))
assert not set(train) & set(hold)
for i in by: by[i].sort(key=lambda x: x[0])
def out(path, evs):
    with open(path, 'w') as f:
        for _, name, props in evs: f.write(json.dumps({'name': name, 'props': props}, ensure_ascii=False, separators=(',', ':')) + '\n')
big = [i for i in hold if len(by[i]) >= 3000]; random.shuffle(big)
slices = []
for n, i in enumerate(big[:20]):
    start = random.randrange(0, len(by[i]) - 3000 + 1); out(f'data/puzzle_slice_{n:02d}.jsonl', by[i][start:start + 3000]); slices.append(dict(install=i, start=start, events=3000, total=len(by[i])))
# 100k: windows of 1000 from random holdout installs
w = []; order = hold[:]
while len(w) < 100000:
    i = random.choice(order)
    if len(by[i]) < 1000: continue
    s = random.randrange(0, len(by[i]) - 1000 + 1); w += by[i][s:s + 1000]
out('data/puzzle_hold_100k.jsonl', w[:100000])
t = []; tr = train[:]
while len(t) < 20000:
    i = random.choice(tr)
    if len(by[i]) < 1000: continue
    s = random.randrange(0, len(by[i]) - 1000 + 1); t += by[i][s:s + 1000]
out('data/puzzle_train_20k.jsonl', t[:20000])
json.dump(dict(train_installs=len(train), hold_installs=len(hold), train_events=sum(len(by[i]) for i in train), hold_events=sum(len(by[i]) for i in hold), overlap=len(set(train) & set(hold)), slice_installs=slices), open('data/split_report.json', 'w'), indent=1)
print('train', len(train), 'hold', len(hold), 'slices', len(slices))
