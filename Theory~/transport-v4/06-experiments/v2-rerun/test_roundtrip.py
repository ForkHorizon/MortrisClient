"""V1/V2 equivalence + decoder robustness (evidence only, NOT product code).

1. Every batch -> MTB2 -> decode -> rebuilt V1 JSON body must be BYTE-IDENTICAL to the real V1 body with event_id
   fields removed (the one agreed difference: identity becomes (install_id, sequence)). Plain and CAS modes,
   base and rich profiles.
2. Hand-written edge cases: ulong max, decimal, double vs float, negative ints, null, unicode, uppercase hex,
   empty properties, same key with different types, sequence gaps, several sessions in one batch.
3. Crude mutation fuzz: decoder may only raise "malformed input" style exceptions.
Run: python test_roundtrip.py"""
import random
from decimal import Decimal
from types import SimpleNamespace

from gen import dataset
from wire import PROJECT_ID, SDK_NAME, SDK_VERSION, mtb2_decode, mtb2_encode, v1_json

EXPECTED_ERRORS = (ValueError, IndexError, KeyError, UnicodeDecodeError, TypeError, StopIteration)


def check(inst, batch, known=None, ctx_cache=None, shape_cache=None):
    sec = {}
    buf = mtb2_encode(inst, batch, known=known, sections=sec)
    meta, ev = mtb2_decode(buf, ctx_cache, shape_cache)
    assert meta["install_id"] == inst.install_id
    assert (meta["project_id"], meta["sdk"]["name"], meta["sdk"]["version"]) == (PROJECT_ID, SDK_NAME, SDK_VERSION)
    assert meta["sent_at_ms"] == batch[-1]["ts"] + 250
    want = v1_json(inst, batch, without_event_id=True)
    got = v1_json(SimpleNamespace(install_id=meta["install_id"]), ev, without_event_id=True)
    assert want == got, (want[:400], got[:400])
    return sec["fps"]


def edge_cases():
    inst = SimpleNamespace(install_id="0b6f6a4e-27c2-4c39-8f3e-6a2b9a4f1c10")
    dev = dict(app_version="1.2.3", build_number="unknown", platform="android", os_version="Android OS 9 / API-28",
               device_class="unknown", locale="und", timezone_offset_minutes=-210)
    base = 1_790_000_000_000
    props = [
        {"u64": 2 ** 64 - 1, "i64min": -2 ** 63, "neg": -5, "dec": Decimal("123.4500"), "d": 0.1, "f": 0.5},
        {},
        {"nul": None, "uni": "Привет, 🌍 \"q\" \\ / \n\t", "HEX": "ABCDEF0123456789ABCDEF", "hex": "00ff" * 8},
        {"mixed": 1}, {"mixed": "one"}, {"mixed": 1.25}, {"mixed": True},
        {"x": 1, "y": 1, "z": "same", "w": "same"},  # alias candidates
    ]
    batch = []
    for i, p in enumerate(props):
        batch.append({"session_id": "11111111-2222-4333-8444-55555555555" + str(i % 2), "name": f"edge_{i % 3}",
                      "ts": base + i * 7 - (3 if i == 4 else 0), "session_elapsed_ms": i * 7 + (i % 2) * 100000,
                      **dev, "properties": p, "sequence": 1000 + i + (5 if i > 3 else 0)})
    check(inst, batch)
    check(inst, batch[:1])


def main():
    n_batches = n_events = 0
    for rich in (False, True):
        for inst, batches in dataset(1, installs=10, rich=rich):
            known, ctx_cache, shape_cache = set(), {}, {}
            for b in batches:
                check(inst, b)
                known |= check(inst, b, set(known), ctx_cache, shape_cache)
                n_batches += 1
                n_events += len(b)
    print(f"V1-equivalence OK (byte-identical minus event_id): {n_batches} batches, {n_events} events, plain + CAS")
    edge_cases()
    print("edge cases OK")

    rng = random.Random(7)
    inst, batches = dataset(1, installs=1)[0]
    seeds = [mtb2_encode(inst, b) for b in batches[:20]]
    bad = 0
    for _ in range(20000):
        s = bytearray(rng.choice(seeds))
        for _ in range(rng.randint(1, 8)):
            op = rng.random()
            if op < 0.5 and s:
                s[rng.randrange(len(s))] = rng.randrange(256)
            elif op < 0.75 and s:
                i = rng.randrange(len(s))
                del s[i:i + rng.randint(1, 16)]
            else:
                i = rng.randrange(len(s) + 1)
                s[i:i] = rng.randbytes(rng.randint(1, 8))
        try:
            mtb2_decode(bytes(s), {}, {})
        except EXPECTED_ERRORS:
            pass
        except Exception as ex:  # anything else is a decoder bug
            bad += 1
            print("unexpected", type(ex).__name__, ex)
    print(f"fuzz: 20000 mutated inputs, unexpected exception types: {bad}")
    assert bad == 0


if __name__ == "__main__":
    main()
