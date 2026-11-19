#!/usr/bin/env python3
"""A synthetic 'generic game' event stream (levels, purchases, ads, position samples with floats) and catalog variants for byte-cost experiments.
Usage: make_generic_game.py OUTDIR [N_EVENTS]. Variants: floats_raw (Unity-like float32 values printed with their shortest text), floats_2dp (rounded to 2 decimals),
floats_scaled_int (the same 2-decimal values as integers x100: the lower bound for a fixed-point encoding)."""
import json, os, random, struct, sys
out = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 60000
random.seed(7)
INT, STR, F64 = 0, 1, 4
def f32(x):  # the float32 a Unity game holds, as the shortest decimal text a JSON writer would print
    b = struct.pack('<f', x); v = struct.unpack('<f', b)[0]
    for p in range(1, 10):
        t = float(f'{v:.{p}g}')
        if struct.unpack('<f', struct.pack('<f', t))[0] == v: return t
    return v
modes = ["easy", "normal", "hard"]; items = ["gem_pack_s", "gem_pack_m", "no_ads", "starter_bundle"]; nets = ["admob", "applovin", "unity_ads"]
def gen():
    ev = []; level = 1; x = y = z = 0.0; t = 0.0
    while len(ev) < N:
        r = random.random()
        if r < 0.05:
            ev.append(("level_start", {"level": level, "mode": random.choice(modes)}))
        elif r < 0.10:
            ev.append(("level_end", {"level": level, "score": random.randint(100, 90000), "time_s": random.uniform(20, 300), "stars": random.randint(0, 3), "coins": random.randint(0, 400), "won": random.random() < 0.7}))
            if random.random() < 0.6: level += 1
        elif r < 0.11:
            ev.append(("purchase", {"item": random.choice(items), "price": random.choice([0.99, 1.99, 4.99, 9.99]), "currency": "USD"}))
        elif r < 0.15:
            ev.append(("ad_impression", {"network": random.choice(nets), "revenue": random.uniform(0.0005, 0.02), "placement": random.choice(["interstitial", "rewarded"])}))
        else:
            x += random.gauss(0, 1.5); y += random.gauss(0, 1.5); z += random.gauss(0, 0.3); t += random.uniform(0.2, 1.0)
            ev.append(("position_sample", {"x": x, "y": y, "z": z, "speed": random.uniform(0, 12), "t": t}))
    return ev
FLOATS = {"time_s", "price", "revenue", "x", "y", "z", "speed", "t"}
events = gen()
def write(name, conv):
    cat_shapes = {}
    lines = []
    for nm, p in events:
        q = {}; fields = []
        for k, v in p.items():
            kind = STR if isinstance(v, str) else (INT if isinstance(v, (int, bool)) and not isinstance(v, float) else F64)
            if isinstance(v, bool): kind = 2
            if k in FLOATS:
                v, kind = conv(k, v)
            q[k] = v; fields.append((k, kind))
        cat_shapes.setdefault((nm, tuple(sorted(fields))), 1)
        lines.append(json.dumps({"name": nm, "props": q}, separators=(",", ":")))
    shapes = [[n, [[k, t] for k, t in f]] for (n, f) in cat_shapes]
    names = sorted({s[0] for s in shapes}); keys = sorted({k for s in shapes for k, _ in s[1]}); pos = {k: i for i, k in enumerate(keys)}
    cat = {"project_id": "generic_game", "events": {n: i + 1 for i, n in enumerate(names)}, "keys": keys, "shapes": shapes, "masks": [sum(1 << pos[k] for k, _ in s[1]) for s in shapes]}
    d = os.path.join(out, name); os.makedirs(d, exist_ok=True)
    json.dump(cat, open(os.path.join(d, "catalog.json"), "w"), separators=(",", ":")); open(os.path.join(d, "events.jsonl"), "w").write("\n".join(lines) + "\n")
    return name
os.makedirs(out, exist_ok=True)
F32 = 3
def exact32(v): return struct.unpack('<f', struct.pack('<f', v))[0]
def nudge(v):
    # the encoder types a number float32 when it is exactly a float32 and int when it is integral (a V1 JSON-compatibility rule that makes the shape of a
    # float field unstable, see PROTOCOL.md); keep every value float64-typed so only the byte cost is measured
    for i in range(1, 60):
        if exact32(v) != v and v != int(v): return v
        v = v + (abs(v) * 1e-9 + 1e-7) * i
    raise SystemExit("cannot nudge %r" % v)
def f32v(v):
    v = exact32(v)
    for i in range(60):
        if v != int(v): return v
        v = exact32(v + 0.37)
    raise SystemExit("cannot make non-integral %r" % v)
names = [write("floats_as_double", lambda k, v: (nudge(f32(v)), F64)),
         write("floats_2dp_as_double", lambda k, v: (nudge(round(v, 2)), F64)),
         write("floats_float32", lambda k, v: (f32v(v), F32)),
         write("floats_2dp_float32", lambda k, v: (f32v(round(v, 2)), F32)),
         write("floats_scaled_int", lambda k, v: (int(round(v * 100)), INT))]
open(os.path.join(out, "manifest.txt"), "w").write("\n".join(names) + "\n")
print(names)
