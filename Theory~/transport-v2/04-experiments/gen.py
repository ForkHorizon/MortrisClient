"""Synthetic event stream generator for transport-V2 experiments (evidence only, NOT product code).

Models a puzzle game integrating the Mortris SDK 0.2.0:
  * V1 envelope/event shape copied from Runtime/Internal/PersistenceEventSerializer.cs + AnalyticsQueue.java
    (payload_json = serializer output + "sequence" appended).
  * Event mix and duplicate fields from the game report quoted in Theory~/event-transport-optimization.md
    (4 core interaction events ~87%, attempt_id == wave_attempt_id, app_version duplicated in properties,
    64-hex placed_state_hash).
  * Batching copied from AnalyticsUploader: flush when 30 s elapsed or >= 50 pending, drain in chunks of <= 100.

Every property NAME/value distribution below is an assumption (marked in 04-experiments/README.md).
Deterministic: same seed -> same bytes.
"""
import hashlib
import random
import uuid
from datetime import datetime, timezone

DEVICES = [
    ("android", "Android OS 14 / API-34 (UP1A.231005.007/S911BXXU3BWK5)", "samsung SM-S911B", "en-US", 120),
    ("android", "Android OS 13 / API-33 (TP1A.220624.014/A145FXXS4BWL1)", "samsung SM-A145F", "de-DE", 60),
    ("android", "Android OS 12 / API-31 (SKQ1.211019.001/V13.0.6.0.SKFMIXM)", "Xiaomi Redmi Note 10", "ru-RU", 180),
    ("android", "Android OS 14 / API-34 (AP1A.240505.005/11520342)", "Google Pixel 7", "en-GB", 0),
    ("android", "Android OS 11 / API-30 (RP1A.200720.012/M127FXXU3BVK1)", "samsung SM-M127F", "pt-BR", -180),
]
APP_VERSIONS = ["1.1.13", "1.1.14"]
BLOCK_TYPES = ["beam_s", "beam_m", "beam_l", "wall_2x1", "wall_2x2", "roof_a", "roof_b", "window", "door", "pillar"]
PROJECT_ID = "mortris-puzzle-prod"


def iso_ms(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms % 1000:03d}Z"


def f32(x):
    """Round a Python float to float32 precision (C# float), then shortest round-trip repr like C# "R"."""
    import struct
    return struct.unpack("<f", struct.pack("<f", x))[0]


class Install:
    def __init__(self, rng, idx):
        self.rng = rng
        self.install_id = str(uuid.UUID(int=rng.getrandbits(128), version=4))
        self.credential = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_") for _ in range(43))
        self.device = DEVICES[idx % len(DEVICES)]
        self.app_version = APP_VERSIONS[min(1, idx % 3)]
        self.build_number = uuid.UUID(int=rng.getrandbits(128)).hex  # Application.buildGUID default (32 hex)
        self.seq = 0
        self.city, self.house, self.attempt_number = 1, 1, 0


def gen_install_events(rng, inst, t0_ms, sessions, rich=False):
    """Return list of logical events (dicts) for one install, in creation order."""
    out = []
    t = t0_ms
    for _ in range(sessions):
        session_id = str(uuid.UUID(int=rng.getrandbits(128), version=4))
        s_start = t
        drift = 0  # stopwatch vs wall clock residual (ms), random walk
        active_ms = 0
        state_hash = hashlib.sha256(rng.randbytes(8)).hexdigest()
        placed = 0

        mem = rng.randint(900, 2500)
        placed_list = []

        def emit(name, props, when):
            nonlocal drift, mem
            if rich and name in ("detail_taken", "detail_released", "placement_resolved", "state_checkpoint"):
                # "rich" profile: extra noisy telemetry so totals match the game report (~1.1 KB raw / ~170 B gzip)
                mem += rng.randint(-6, 6)
                props = {**props, "frame_ms": f32(rng.uniform(8, 40)), "fps": rng.randint(24, 61),
                         "free_memory_mb": mem, "camera_zoom": f32(1 + 0.05 * props.get("wave_index", 1)),
                         "touch_x": f32(rng.uniform(0, 1)), "touch_y": f32(rng.uniform(0, 1)),
                         "since_last_action_ms": rng.randint(0, 20000), "ui_layer": rng.choice(["hud", "tray", "board"])}
                if name == "state_checkpoint":
                    props["placed_block_ids"] = ",".join(map(str, placed_list))
                    props["house_progress"] = f32(len(placed_list) / 40)
                    props["board_rows"] = ";".join("".join(rng.choice("01") for _ in range(8)) for _ in range(10))
            inst.seq += 1
            if rng.random() < 0.05:
                drift += rng.choice((-1, 1))
            out.append({
                "event_id": str(uuid.UUID(int=rng.getrandbits(128), version=4)),
                "session_id": session_id, "name": name, "ts": when,
                "session_elapsed_ms": when - s_start + drift,
                "app_version": inst.app_version, "build_number": inst.build_number,
                "platform": inst.device[0], "os_version": inst.device[1], "device_class": inst.device[2],
                "locale": inst.device[3], "timezone_offset_minutes": inst.device[4],
                "properties": props, "sequence": inst.seq,
            })

        emit("session_start", {"launch_type": rng.choice(["cold", "warm"]), "first_session": inst.seq == 0,
                               "app_version": inst.app_version}, t)
        t += rng.randint(800, 4000)
        for _attempt in range(rng.randint(1, 3)):
            inst.attempt_number += 1
            attempt_id = str(uuid.UUID(int=rng.getrandbits(128), version=4))
            base = lambda: {"app_version": inst.app_version, "attempt_id": attempt_id, "wave_attempt_id": attempt_id,
                            "city_id": inst.city, "house_id": inst.house, "attempt_number": inst.attempt_number}
            emit("attempt_started", {**base(), "difficulty": rng.choice(["normal", "hard"]),
                                     "total_block_count": 40}, t)
            placed = 0
            placed_list.clear()
            waves = rng.randint(3, 5)
            won = rng.random() < 0.7
            for wave in range(1, waves + 1):
                t += rng.randint(300, 1500)
                emit("wave_started", {**base(), "wave_index": wave, "blocks_in_wave": rng.randint(6, 12)}, t)
                for _i in range(rng.randint(5, 12)):
                    think = int(rng.lognormvariate(8.0, 0.8))  # median ~3 s between interactions
                    t += think
                    active_ms += think
                    block_id = rng.randint(1, 40)
                    btype = rng.choice(BLOCK_TYPES)
                    slot = rng.randint(0, 4)
                    emit("detail_taken", {**base(), "wave_index": wave, "block_id": block_id, "block_type": btype,
                                          "slot_index": slot, "active_elapsed_ms": active_ms,
                                          "placed_block_count": placed}, t)
                    drag = int(rng.lognormvariate(6.6, 0.5))  # median ~730 ms
                    t += drag
                    active_ms += drag
                    cx, cy = rng.randint(0, 7), rng.randint(0, 9)
                    emit("detail_released", {**base(), "wave_index": wave, "block_id": block_id,
                                             "block_type": btype, "drag_ms": drag,
                                             "release_x": f32(rng.uniform(-3, 3)), "release_y": f32(rng.uniform(-1, 6)),
                                             "target_cell_x": cx, "target_cell_y": cy,
                                             "active_elapsed_ms": active_ms}, t)
                    t += rng.randint(8, 40)
                    ok = rng.random() < 0.82
                    if ok:
                        placed += 1
                        placed_list.append(block_id)
                        state_hash = hashlib.sha256(state_hash.encode() + bytes([block_id, cx, cy])).hexdigest()
                    emit("placement_resolved", {**base(), "wave_index": wave, "block_id": block_id,
                                                "block_type": btype, "outcome": "placed" if ok else "rejected",
                                                "cell_x": cx, "cell_y": cy, "rotation": rng.choice([0, 90, 180, 270]),
                                                "snap_distance": f32(rng.uniform(0, 0.5)),
                                                "placed_block_count": placed, "placed_state_hash": state_hash,
                                                "active_elapsed_ms": active_ms + 20}, t)
                    t += rng.randint(1, 6)
                    emit("state_checkpoint", {**base(), "wave_index": wave, "placed_block_count": placed,
                                              "remaining_block_count": 40 - placed, "placed_state_hash": state_hash,
                                              "moves_count": placed + rng.randint(0, 3),
                                              "active_elapsed_ms": active_ms + 22}, t)
                    if rng.random() < 0.04:
                        t += rng.randint(200, 900)
                        emit("hint_used", {**base(), "wave_index": wave, "hint_type": rng.choice(["lamp", "blueprint"]),
                                           "hints_left": rng.randint(0, 3)}, t)
                    if rng.random() < 0.05:
                        t += rng.randint(100, 2000)
                        emit("ui_click", {"app_version": inst.app_version, "screen": "gameplay",
                                          "element": rng.choice(["pause", "settings", "booster", "undo"])}, t)
                t += rng.randint(500, 2000)
                emit("wave_completed", {**base(), "wave_index": wave, "placed_block_count": placed,
                                        "active_elapsed_ms": active_ms}, t)
            t += rng.randint(500, 3000)
            emit("attempt_finished", {**base(), "outcome": "win" if won else "lose", "placed_block_count": placed,
                                      "active_elapsed_ms": active_ms, "score": rng.randint(100, 5000)}, t)
            if won:
                inst.house += 1
                if inst.house > 6:
                    inst.house, inst.city = 1, inst.city + 1
            if rng.random() < 0.3:
                t += rng.randint(2000, 8000)
                emit("ad_impression", {"app_version": inst.app_version, "ad_format": "interstitial",
                                       "placement": "between_attempts", "network": rng.choice(["admob", "unity"])}, t)
        t += rng.randint(3600_000, 30 * 3600_000)  # gap between sessions
    return out


def batches_for(rng, events, offline_prob=0.15, interval_ms=30_000, threshold=50, max_batch=100):
    """Replay AnalyticsUploader cadence. Returns list of event lists (batch boundaries).
    Offline sessions accumulate and flush at the next online session start."""
    out, pending, last_flush = [], [], None
    online = True
    cur_session = None
    for e in events:
        if e["session_id"] != cur_session:
            # session boundary: app was backgrounded/killed; previous session flushed on pause only if online
            if online and pending:
                out.extend(pending[i:i + max_batch] for i in range(0, len(pending), max_batch))
                pending = []
            cur_session = e["session_id"]
            online = rng.random() > offline_prob
            last_flush = e["ts"]
            if online and pending:
                out.extend(pending[i:i + max_batch] for i in range(0, len(pending), max_batch))
                pending = []
        pending.append(e)
        if online and (e["ts"] - last_flush >= interval_ms or len(pending) >= threshold):
            out.extend(pending[i:i + max_batch] for i in range(0, len(pending), max_batch))
            pending, last_flush = [], e["ts"]
    if pending:
        out.extend(pending[i:i + max_batch] for i in range(0, len(pending), max_batch))
    return out


def dataset(seed, installs=60, sessions=(2, 6), rich=False):
    """Return list of (Install, batches)."""
    rng = random.Random(seed)
    res = []
    for i in range(installs):
        inst = Install(rng, i)
        ev = gen_install_events(rng, inst, 1_790_000_000_000 + rng.randint(0, 10**9), rng.randint(*sessions), rich)
        res.append((inst, batches_for(rng, ev)))
    return res


if __name__ == "__main__":
    from collections import Counter
    import sys
    ds = dataset(1, rich="rich" in sys.argv)
    allev = [e for _, bs in ds for b in bs for e in b]
    sizes = [len(b) for _, bs in ds for b in bs]
    c = Counter(e["name"] for e in allev)
    print("events", len(allev), "batches", len(sizes), "mean batch", round(sum(sizes) / len(sizes), 1))
    for k, v in c.most_common():
        print(f"  {k:20s} {v:6d} {100 * v / len(allev):5.1f}%")
    hist = Counter(min(s // 10 * 10, 100) for s in sizes)
    print("batch size histogram (bucket of 10):", dict(sorted(hist.items())))
