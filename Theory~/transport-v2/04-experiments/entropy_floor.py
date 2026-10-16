"""Analytic entropy floor of the BASE generator (gen.py), i.e. the information no lossless codec can remove.
This is an ESTIMATE for the synthetic data only; real data has an unknown floor (07-open-questions.md).
Run: python entropy_floor.py"""
import math

LN2 = math.log(2)


def lognormal_bits(mu, sigma):
    # differential entropy of a lognormal in nats, quantized to 1 ms -> discrete entropy ~= h (bits)
    return (mu + 0.5 * math.log(2 * math.pi * math.e * sigma ** 2)) / LN2


def f32_uniform_bits(lo, hi):
    # entropy of float32(U(lo,hi)): ~= log2(range / mean ulp); estimate mean ulp from mean magnitude
    mag = (abs(lo) + abs(hi)) / 2 / 2 if lo < 0 < hi else (lo + hi) / 2
    ulp = 2.0 ** (math.floor(math.log2(mag)) - 23)
    return math.log2((hi - lo) / ulp)


def h(p):
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))


per_interaction = {
    "think time (lognormal 8, 0.8)": lognormal_bits(8.0, 0.8),
    "drag ms (lognormal 6.6, 0.5)": lognormal_bits(6.6, 0.5),
    "block_id U(1..40)": math.log2(40),
    "block_type 1/10": math.log2(10),
    "slot_index U(0..4)": math.log2(5),
    "cell x,y U(8)xU(10)": math.log2(80),
    "rotation 1/4": 2,
    "placed? p=0.82": h(0.82),
    "release_x f32 U(-3,3)": f32_uniform_bits(-3, 3),
    "release_y f32 U(-1,6)": f32_uniform_bits(-1, 6),
    "snap_distance f32 U(0,0.5)": f32_uniform_bits(0, 0.5),
    "new SHA-256 state hash x0.82": 256 * 0.82,
    "resolve offset U(8..40) + checkpoint offset U(1..6)": math.log2(33) + math.log2(6),
    "moves_count noise U(0..3)": 2,
    "elapsed drift step (p=.05 per event, 4 events)": 4 * (h(0.05) + 0.05),
}
bits = sum(per_interaction.values())
for k, v in per_interaction.items():
    print(f"{k:55s} {v:7.1f} bits")
# ~91% of events are the 4-event interaction; the rest (wave/attempt/session/ui/hint/ad) add little entropy
# besides new UUIDs: attempt_id (122 bits) per ~45 interactions, session_id (122 bits) per ~70 interactions.
rare = (122 / 45 + 122 / 70 + 40) / 1  # + ~40 bits/interaction for rare events' own random fields (generous)
total = bits + rare
print(f"\nper interaction (4 core events + share of rare events): {total:.0f} bits = {total / 8:.1f} B")
print(f"per event (interaction ~= 4.4 events incl. rare ones): {total / 8 / 4.4:.1f} B/event")
print(f"  of which SHA-256 hashes: {256 * 0.82 / 8 / 4.4:.1f} B/event, floats: "
      f"{(per_interaction['release_x f32 U(-3,3)'] + per_interaction['release_y f32 U(-1,6)'] + per_interaction['snap_distance f32 U(0,0.5)']) / 8 / 4.4:.1f} B/event")
