#!/usr/bin/env python3
"""Builds catalog/event variants for byte-cost experiments: each variant drops or retypes properties in the replay events and in the catalog shapes.
Usage: make_ablation.py CATALOG REPLAY OUTDIR [N_EVENTS]. Writes OUTDIR/<variant>/{catalog.json,events.jsonl} and OUTDIR/manifest.txt."""
import json, os, sys
INT = 0
catalog = json.load(open(sys.argv[1])); replay = [json.loads(l) for l in open(sys.argv[2])]
out = sys.argv[3]; N = int(sys.argv[4]) if len(sys.argv) > 4 else 10000
replay = replay[:N]
os.makedirs(out, exist_ok=True)

def rebuild(cat):
    names = sorted({s[0] for s in cat["shapes"]})
    cat["events"] = {n: i + 1 for i, n in enumerate(names)}
    cat["keys"] = sorted({k for s in cat["shapes"] for k, _ in s[1]})
    pos = {k: i for i, k in enumerate(cat["keys"])}
    cat["masks"] = [sum(1 << pos[k] for k, _ in s[1]) for s in cat["shapes"]]
    return cat

def variant(name, drop=(), to_int=()):
    cat = json.loads(json.dumps(catalog))
    cat["shapes"] = [[s[0], [[k, (INT if k in to_int else t)] for k, t in s[1] if k not in drop]] for s in cat["shapes"]]
    seen, unique = set(), []
    for sh in cat["shapes"]:
        key = json.dumps(sh)
        if key not in seen: seen.add(key); unique.append(sh)   # dropping a property can make two shapes identical
    cat["shapes"] = unique
    rebuild(cat)
    counters = {k: {} for k in to_int}
    lines = []
    for e in replay:
        p = {}
        for k, v in e["props"].items():
            if k in drop: continue
            if k in to_int:
                m = counters[k]; v = m.setdefault(v, len(m) + 1)
            p[k] = v
        lines.append(json.dumps({"name": e["name"], "props": p}, separators=(",", ":")))
    d = os.path.join(out, name); os.makedirs(d, exist_ok=True)
    json.dump(cat, open(os.path.join(d, "catalog.json"), "w"), separators=(",", ":"))
    open(os.path.join(d, "events.jsonl"), "w").write("\n".join(lines) + "\n")
    return name

names = [variant("baseline")]
keys = sorted({k for e in replay for k in e["props"]})
for k in keys: names.append(variant("drop_" + k, drop=(k,)))
CONST = ("origin", "schema_version", "progress_origin", "coordinate_space", "app_version")
names.append(variant("drop_constants", drop=CONST))
names.append(variant("ids_to_numbers", to_int=("attempt_id", "house_run_id", "interaction_id", "wave_attempt_id")))
D9D10 = ("wave_attempt_id", "interaction_id", "placed_state_hash")
names.append(variant("v8_decided", drop=D9D10, to_int=("attempt_id", "house_run_id")))
names.append(variant("v8_decided_plus_constants", drop=D9D10 + CONST, to_int=("attempt_id", "house_run_id")))
names.append(variant("no_properties", drop=tuple(keys)))
open(os.path.join(out, "manifest.txt"), "w").write("\n".join(names) + "\n")
print(len(names), "variants")
