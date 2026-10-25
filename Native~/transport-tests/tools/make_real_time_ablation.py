#!/usr/bin/env python3
"""Variants on events with their REAL timestamps (from the exported corpus): Usage: make_real_time_ablation.py CATALOG CORPUS.jsonl.gz OUTDIR [N_LINES].
Events are ordered by (install, sequence) and filtered to shapes the catalog knows; each line carries "ts" and "el" for the harness."""
import gzip, json, os, sys
from datetime import datetime
catalog = json.load(open(sys.argv[1])); out = sys.argv[3]; N = int(sys.argv[4]) if len(sys.argv) > 4 else 300000
os.makedirs(out, exist_ok=True)
INT = 0
known = {(s[0], tuple(k for k, _ in s[1])) for s in catalog["shapes"]}
rows = []
with gzip.open(sys.argv[2], "rt") as f:
    for i, line in enumerate(f):
        if i >= N: break
        d = json.loads(line); p = d["properties"]
        if (d["name"], tuple(sorted(p))) not in known: continue
        rows.append((d["install_id"], d["sequence"], d["name"], p, int(datetime.fromisoformat(d["occurred_at_client"]).timestamp() * 1000), d["session_elapsed_ms"]))
rows.sort(key=lambda r: (r[0], r[1]))
rows = rows[: (len(rows) // 100) * 100]
print("events", len(rows))
D = ("wave_attempt_id", "interaction_id", "placed_state_hash")
def rebuild(cat):
    cat["events"] = {n: i + 1 for i, n in enumerate(sorted({s[0] for s in cat["shapes"]}))}
    cat["keys"] = sorted({k for s in cat["shapes"] for k, _ in s[1]}); pos = {k: i for i, k in enumerate(cat["keys"])}
    cat["masks"] = [sum(1 << pos[k] for k, _ in s[1]) for s in cat["shapes"]]
def variant(name, drop=(), to_int=(), paused=None):
    cat = json.loads(json.dumps(catalog)); shapes = []
    for s in cat["shapes"]:
        fields = []
        for k, t in s[1]:
            if k in drop: continue
            if paused and k == "active_elapsed_ms": k, t = "paused_ms", INT
            fields.append([k, INT if k in to_int else t])
        shapes.append([s[0], sorted(fields)])
    seen, uniq = set(), []
    for s in shapes:
        j = json.dumps(s)
        if j not in seen: seen.add(j); uniq.append(s)
    cat["shapes"] = uniq; rebuild(cat)
    counters = {k: {} for k in to_int}; attempt0 = {}; lines = []
    for inst, seq, nm, p, ts, el in rows:
        q = {}
        for k, v in p.items():
            if k in drop: continue
            if k == "active_elapsed_ms" and paused:
                a = p["attempt_id"]; t0, a0 = attempt0.setdefault((inst, a), (ts, v))
                r = (ts - t0) - (v - a0)
                k, v = "paused_ms", (max(0, r) if paused == "clean" else r)
            elif k in to_int:
                m = counters[k]; v = m.setdefault((inst, v), len(m) + 1)
            q[k] = v
        lines.append(json.dumps({"name": nm, "props": q, "ts": ts, "el": el}, separators=(",", ":")))
    d = os.path.join(out, name); os.makedirs(d, exist_ok=True)
    json.dump(cat, open(os.path.join(d, "catalog.json"), "w"), separators=(",", ":")); open(os.path.join(d, "events.jsonl"), "w").write("\n".join(lines) + "\n")
    return name
names = [variant("real_baseline"), variant("real_v8", drop=D, to_int=("attempt_id", "house_run_id")),
         variant("real_v8_paused", drop=D, to_int=("attempt_id", "house_run_id"), paused="noisy"),
         variant("real_v8_paused_clean", drop=D, to_int=("attempt_id", "house_run_id"), paused="clean"),
         variant("real_v8_no_active", drop=D + ("active_elapsed_ms",), to_int=("attempt_id", "house_run_id"))]
if os.environ.get("PER_KEY"):
    base = ("wave_attempt_id", "interaction_id", "placed_state_hash")
    keys = sorted({k for r in rows for k in r[3]} - set(base))
    names = [variant("real_v8", drop=D, to_int=("attempt_id", "house_run_id"))]
    for k in keys: names.append(variant("v8_drop_" + k, drop=D + (k,), to_int=tuple(x for x in ("attempt_id", "house_run_id") if x != k)))
open(os.path.join(out, "manifest.txt"), "w").write("\n".join(names) + "\n")
