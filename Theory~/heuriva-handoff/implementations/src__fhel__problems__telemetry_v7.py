"""Bounded local bridge to the frozen MORTRIS M7 encoder and Go decoder."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[3]


def _handoff_root() -> Path:
    candidates = (ROOT / "MORTRIS_handoff-v7~", ROOT / "MortrisV7Data/snapshots/MORTRIS_handoff-v7~")
    return next((path for path in candidates if (path / "docs/Theory~/transport-v7/06-experiments/results/catalog-real-raw.json").is_file()), candidates[0])


HANDOFF = _handoff_root()
EXPERIMENTS = HANDOFF / "docs/Theory~/transport-v7/06-experiments"
CATALOG = EXPERIMENTS / "results/catalog-real-raw.json"
DICTIONARIES = {size: EXPERIMENTS / f"results/dict-real-raw-{size}.bin" for size in (16_384, 32_768)}
REPLAY = ROOT / ".local/telemetry-research/v7-replay"
CSHARP = REPLAY / "bin/net10.0/Mortris.V7Replay.dll"
GO = REPLAY / "bin/v7-decode"
CSHARP_SOURCES = (
    "M7Aliases.cs", "M7Catalog.cs", "M7Columns.cs", "M7Event.cs", "M7EventEncoder.cs",
    "M7FrameEncoder.cs", "M7Zstd.cs", "MiniJson.cs",
)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def assets_available() -> bool:
    """True when the private MORTRIS handoff (catalog, dictionaries, pinned zstd) is present; it is an optional input."""
    return CATALOG.is_file() and (HANDOFF / "client/Native~/zstd/SHA256SUMS").is_file()


def catalog() -> dict[str, Any]:
    if not assets_available():
        raise ValueError("v7_assets_unavailable: the private MORTRIS handoff is not installed")
    return json.loads(CATALOG.read_text())


def asset_identity() -> bytes:
    # Without the handoff no M7 measurement can run (measure() refuses), so a stable explicit marker is the honest
    # identity; it never equals the identity of a run that had the real assets.
    if not assets_available():
        return b'{"v7_assets":"unavailable"}'
    files = [CATALOG, *DICTIONARIES.values(), HANDOFF / "client/Native~/zstd/SHA256SUMS",
             ROOT / "research/telemetry-v7/Mortris.V7Replay.csproj", ROOT / "research/telemetry-v7/Directory.Build.props",
             ROOT / "research/telemetry-v7/Program.cs", ROOT / "research/telemetry-v7/go/go.mod",
             ROOT / "research/telemetry-v7/go/go.sum", ROOT / "research/telemetry-v7/go/main.go"]
    files.extend(HANDOFF / f"client/Runtime/Internal/Transport/{name}" for name in CSHARP_SOURCES)
    files.extend(sorted((HANDOFF / "server/internal/transportv7").glob("*.go")))
    files.append(native_library())
    return json.dumps({str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path): _sha(path)
                       for path in files}, sort_keys=True, separators=(",", ":")).encode()


def native_library() -> Path:
    manifest = HANDOFF / "client/Native~/zstd/SHA256SUMS"
    for line in manifest.read_text().splitlines():
        expected, name = line.split(None, 1)
        path = Path(name.strip())
        if path.name == "libdaliys_zstd.dylib" and path.is_file() and _sha(path) == expected:
            return path
    raise ValueError("pinned local V7 zstd library is unavailable")


def _same_value(expected: Any, actual: Any) -> bool:
    if expected is None or actual is None:
        return expected is actual
    if type(expected) is bool or type(actual) is bool:
        return type(expected) is bool and type(actual) is bool and expected is actual
    if type(expected) is int or type(actual) is int:
        return type(expected) is int and type(actual) is int and expected == actual
    if type(expected) is float or type(actual) is float:
        return (type(expected) is float and type(actual) is float and expected == actual
                and (expected != 0.0 or math.copysign(1.0, expected) == math.copysign(1.0, actual)))
    if type(expected) is str or type(actual) is str:
        return type(expected) is str and type(actual) is str and expected == actual
    if isinstance(expected, list) or isinstance(actual, list):
        return (isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual)
                and all(_same_value(a, b) for a, b in zip(expected, actual, strict=True)))
    if isinstance(expected, dict) or isinstance(actual, dict):
        return (isinstance(expected, dict) and isinstance(actual, dict) and expected.keys() == actual.keys()
                and all(_same_value(expected[k], actual[k]) for k in expected))
    return type(expected) is type(actual) and expected == actual


def _same_event(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    try:
        left = datetime.fromisoformat(str(expected["occurred_at_client"].replace("Z", "+00:00")))
        right = datetime.fromisoformat(str(actual["occurred_at_client"].replace("Z", "+00:00")))
    except (KeyError, ValueError, AttributeError):
        return False
    fields = ("sequence", "session_elapsed_ms", "session_id", "app_version", "build_number", "platform",
              "os_version", "device_class", "locale", "timezone_offset_minutes", "name", "properties")
    return (int(left.timestamp() * 1000) == int(right.timestamp() * 1000)
            and all(field in expected and field in actual and _same_value(expected[field], actual[field]) for field in fields))


def _run(command: list[str], request: bytes, timeout: float) -> dict[str, Any]:
    try:
        result = subprocess.run(command, input=request, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"trusted V7 helper failed: {type(exc).__name__}") from None
    if result.returncode:
        raise ValueError("trusted V7 helper returned a nonzero exit status")
    try:
        value = json.loads(result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("trusted V7 helper returned malformed output") from None
    if not isinstance(value, dict) or value.get("ok") is not True:
        raise ValueError("trusted V7 helper returned an invalid result")
    return value


def measure(request: Mapping[str, Any], repeats: int, timeout: float) -> dict[str, Any]:
    started = time.monotonic()

    def remaining() -> float:
        left = timeout - (time.monotonic() - started)
        if left <= 0:
            raise ValueError("trusted V7 measurement exceeded its time limit")
        return left

    if not assets_available():
        raise ValueError("v7_assets_unavailable: the private MORTRIS handoff is not installed")
    if not CSHARP.is_file() or not GO.is_file():
        raise ValueError("run research/telemetry-v7/build.sh before admitting an M7 study")
    root = json.loads(CATALOG.read_text())
    dictionary_size = request["dictionary_kib"] * 1024
    dictionary_path = DICTIONARIES.get(dictionary_size)
    dictionary = dictionary_path.read_bytes() if dictionary_path else b""
    catalog = CATALOG.read_bytes()
    csharp_request = {key: request[key] for key in ("project_id", "batch_size", "integer_model", "string_model", "samples")}
    csharp_input = json.dumps(csharp_request, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    go_command = [str(GO)]
    expected: dict[tuple[int, int], list[Mapping[str, Any]]] = {}
    runs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    stream_index = 0
    for sample in request["samples"]:
        for local_stream in sample["streams"]:
            for batch_index, batch in enumerate(local_stream["batches"]):
                expected[(stream_index, batch_index)] = batch["events"]
            stream_index += 1

    for _ in range(repeats):
        csharp = _run([shutil.which("dotnet") or "dotnet", str(CSHARP), str(CATALOG),
                       str(dictionary_path) if dictionary_path else "-", str(native_library())], csharp_input, remaining())
        if csharp.get("project_matches") is not True:
            raise ValueError("M7 catalog project identity mismatch")
        go_request = {
            "project_id": root["project_id"],
            "catalog": base64.b64encode(catalog).decode("ascii"),
            "dictionary": base64.b64encode(dictionary).decode("ascii"),
            "streams": csharp["streams"],
        }
        go = _run(go_command, json.dumps(go_request, separators=(",", ":")).encode(), remaining())
        if go.get("decoded_frames") != csharp.get("frames") or go.get("decoded_events") != csharp.get("encoded_events"):
            raise ValueError("independent Go decode did not account for every M7 frame")
        seen: set[tuple[int, int]] = set()
        for frame in go.get("frames", []):
            key = (frame.get("stream_index"), frame.get("batch_index"))
            target = expected.get(key)
            decoded = frame.get("events")
            if target is None or key in seen or not isinstance(decoded, list) or len(target) != len(decoded):
                raise ValueError("independent Go decode returned an unexpected batch")
            if not all(_same_event(source, result) for source, result in zip(target, decoded, strict=True)):
                raise ValueError("independent Go decode did not preserve event semantics")
            seen.add(key)
        if len(seen) != csharp["frames"]:
            raise ValueError("independent Go decode left M7 frames unchecked")
        runs.append((csharp, go))

    csharp, go = runs[-1]
    return {
        "ok": True,
        "rows": csharp["rows"],
        "frames": csharp["frames"],
        "encoded_events": csharp["encoded_events"],
        "fallback_events": csharp["fallback_events"],
        "failure_kinds": csharp["failure_kinds"],
        "fallback_bytes": csharp["fallback_bytes"],
        "alias_records": csharp["alias_records"],
        "asset_bytes": len(catalog) + len(dictionary),
        "catalog_sha256": _sha(CATALOG),
        "dictionary_sha256": hashlib.sha256(dictionary).hexdigest(),
        "encode_ns": sum(run[0]["encode_nanoseconds"] for run in runs) // repeats,
        "decode_ns": sum(run[1]["decode_nanoseconds"] for run in runs) // repeats,
    }

