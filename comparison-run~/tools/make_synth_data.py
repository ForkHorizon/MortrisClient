#!/usr/bin/env python3
"""Three synthetic but structurally different games (flat props only: Mortris and Firebase/GA all take flat parameters), seeded and reproducible.
 casual    - hyper-casual runner: 8 event types, 3-8 small props, ints and a few floats, ids are small ints, high rate of one event type.
 midcore   - RPG/economy: 70 event types, 4-40 props each (long strings incl. unicode/localized text, uuid strings, epoch-ms ints, booleans, optional fields, big ints, nulls-as-absent).
 telemetry - float-heavy: position/performance samples (6-14 float32 values per event) plus a few discrete events.
Outputs data/<name>_slice_NN.jsonl (4 slices x 3000 events, different seeds) and data/<name>_train_20k.jsonl (different seed, used to warm servers only)."""
import json, math, random, struct, uuid
def f32(x):
    v = struct.unpack('<f', struct.pack('<f', x))[0]
    for p in range(1, 10):
        t = float(f'{v:.{p}g}')
        if struct.unpack('<f', struct.pack('<f', t))[0] == v: return t
    return v
WORDS = 'ember glacier quartz meadow harbor falcon willow cobalt saffron tundra orchid basalt lantern monsoon pebble thistle zephyr marrow juniper'.split()
LOC = ['Привет, герой! Твой отряд ждёт.', '勇者よ、道はまだ続く', 'Bem-vindo de volta, aventureiro!', 'Willkommen zurück, Abenteurer — die Burg wartet.', 'Welcome back, adventurer.']
def zipf(rng, n, s=1.2):
    w = [1 / (i + 1) ** s for i in range(n)]; return rng.choices(range(n), w)[0]
def casual(rng, total):
    ev = []; level = 1; score = 0; coins = 0; t0 = 1.7e12
    while len(ev) < total:
        r = rng.random()
        if r < 0.50: ev.append(('obstacle_hit', {'level': level, 'lane': rng.randint(0, 2), 'speed': f32(rng.uniform(3, 14)), 'combo': rng.randint(0, 30)}))
        elif r < 0.75: coins += rng.randint(1, 5); ev.append(('coin_collected', {'level': level, 'amount': rng.randint(1, 5), 'total': coins}))
        elif r < 0.85: ev.append(('level_start', {'level': level, 'mode': rng.choice(['normal', 'hard']), 'lives': rng.randint(1, 5)}))
        elif r < 0.92: score = rng.randint(100, 90000); ev.append(('level_end', {'level': level, 'score': score, 'stars': rng.randint(0, 3), 'won': rng.random() < 0.7, 'time_s': f32(rng.uniform(15, 120))}))
        elif r < 0.96: ev.append(('ad_shown', {'placement': rng.choice(['interstitial', 'rewarded']), 'network': rng.choice(['admob', 'applovin']), 'revenue_usd': f32(rng.uniform(0.0005, 0.03)), 'level': level}))
        elif r < 0.98: level += 1; ev.append(('skin_equipped', {'skin_id': rng.randint(1, 40), 'level': level}))
        elif r < 0.99: ev.append(('iap_purchase', {'sku': rng.choice(['gems_s', 'gems_m', 'no_ads']), 'price_usd': rng.choice([0.99, 1.99, 4.99]), 'level': level}))
        else: ev.append(('session_ping', {'level': level, 'fps_avg': f32(rng.uniform(24, 60)), 'mem_mb': rng.randint(180, 420)}))
    return ev
def midcore(rng, total):
    tr = random.Random('midcore-table'); types = []  # the event-type table is fixed (a game's schema), only the stream differs per slice
    for i in range(70):
        k = tr.randint(4, 40); fields = []
        for j in range(k):
            kind = tr.choice(['int', 'int', 'int', 'str', 'str', 'bool', 'float', 'uuid', 'ts', 'text', 'big'])
            fields.append((f'{tr.choice(WORDS)}_{j}', kind, tr.random() < 0.25))  # (key, kind, optional)
        types.append((f'{tr.choice(WORDS)}_{tr.choice(WORDS)}_{i}', fields))
    ids = [str(uuid.UUID(int=rng.getrandbits(128), version=4)) for _ in range(30)]; ev = []; clock = 1.7e12
    while len(ev) < total:
        name, fields = types[zipf(rng, len(types), 1.0)]; props = {}; clock += rng.randint(50, 4000)
        for key, kind, opt in fields:
            if opt and rng.random() < 0.5: continue
            if kind == 'int': props[key] = rng.randint(0, 5000)
            elif kind == 'str': props[key] = rng.choice(WORDS) + '_' + rng.choice(WORDS)
            elif kind == 'bool': props[key] = rng.random() < 0.5
            elif kind == 'float': props[key] = f32(rng.uniform(0, 1000))
            elif kind == 'uuid': props[key] = rng.choice(ids) if rng.random() < 0.8 else str(uuid.UUID(int=rng.getrandbits(128), version=4))
            elif kind == 'ts': props[key] = int(clock)
            elif kind == 'text': props[key] = rng.choice(LOC) * rng.randint(1, 4)
            else: props[key] = rng.randint(2 ** 40, 2 ** 53)
        ev.append((name, props))
    return ev
def telemetry(rng, total):
    ev = []; x = y = z = 0.0; t = 0.0
    while len(ev) < total:
        r = rng.random()
        if r < 0.80:
            x += rng.gauss(0, 1.5); y += rng.gauss(0, 1.5); z += rng.gauss(0, .3); t += rng.uniform(.05, .3)
            ev.append(('pose_sample', {'x': f32(x), 'y': f32(y), 'z': f32(z), 'yaw': f32(rng.uniform(-math.pi, math.pi)), 'speed': f32(rng.uniform(0, 12)), 't': f32(t), 'vx': f32(rng.gauss(0, 3)), 'vy': f32(rng.gauss(0, 3)), 'vz': f32(rng.gauss(0, .5))}))
        elif r < 0.95: ev.append(('perf_sample', {'fps': f32(rng.uniform(20, 60)), 'frame_ms_p99': f32(rng.uniform(16, 70)), 'cpu_ms': f32(rng.uniform(3, 18)), 'gpu_ms': f32(rng.uniform(3, 18)), 'mem_mb': rng.randint(200, 900), 'temp_c': f32(rng.uniform(28, 46)), 'battery': f32(rng.uniform(0.1, 1.0))}))
        else: ev.append(('checkpoint', {'id': rng.randint(1, 60), 'time_s': f32(t), 'deaths': rng.randint(0, 12), 'ghost': rng.random() < 0.3}))
    return ev
def write(path, evs):
    with open(path, 'w') as f:
        for n, p in evs: f.write(json.dumps({'name': n, 'props': p}, ensure_ascii=False, separators=(',', ':')) + '\n')
for name, gen in (('casual', casual), ('midcore', midcore), ('telemetry', telemetry)):
    for s in range(4): write(f'data/{name}_slice_{s:02d}.jsonl', gen(random.Random(f'{name}-slice-{s}'), 3000))
    write(f'data/{name}_train_20k.jsonl', gen(random.Random(f'{name}-train'), 20000))
