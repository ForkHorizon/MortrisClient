"""Bounded, data-only MORTRIS V1 payload research on installation-disjoint real exports."""
from __future__ import annotations

import gzip
import bz2
import hashlib
import json
import lzma
import math
import os
import platform
import sys
import time
import uuid
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .. import campaign_search
from ..campaign_search import DomainSpace, geo_mean, parse_in
from . import Problem, telemetry_code, telemetry_v7

TELEMETRY = "trusted-telemetry-payload"
TELEMETRY_M7 = "trusted-telemetry-m7-payload"
FIELDS = ("event_id", "session_id", "name", "occurred_at_client", "session_elapsed_ms", "app_version", "build_number",
          "platform", "os_version", "device_class", "locale", "timezone_offset_minutes", "properties")
EXPORT_FIELDS = set(FIELDS) | {"project_id", "install_id", "sequence", "event_kind", "effective_at", "clock_skew_ms",
                               "time_quality", "sent_at_client", "received_at"}
STRING_FIELDS = set(FIELDS) - {"session_elapsed_ms", "timezone_offset_minutes", "properties"}
SDK = {"name": "mortris-unity", "version": "0.2.0"}
SENT_AT = "2026-10-20T00:00:00.000Z"
DOMAINS = {family: {"batch_size": (25, 50, 100), "level": (1, 3, 6)}
           for family in ("telemetry", "dictionary", "shared_metadata", "columnar", "delta_columnar")}
DOMAINS["codec_columnar"] = {"batch_size": (100,), "codec": ("gzip", "zlib", "bz2", "lzma"), "level": (3,)}
DOMAINS["v7_frame"] = {"batch_size": (25, 50, 100, 150, 200, 300, 500), "dictionary_kib": (0, 16, 32), "model": ("base", "integer", "string", "both"),
                       "batching": ("fixed", "session")}   # session: also cut a batch where session_id changes (data-side only; the frozen encoder is untouched)
DOMAINS["composable"] = {
    "batch_size": (25, 50, 100, 250),
    "hoist_shared": (False, True),
    "delta_elapsed": (False, True),
    "dict_strings": (False, True),
    "layout": ("row", "columnar"),
    "codec": ("gzip", "zlib", "bz2", "lzma"),
    "level": (1, 3, 6),
}
DOMAINS["code_codec"] = {
    "language": telemetry_code.CODE_LANGUAGES,
    "strategy": telemetry_code.CODE_STRATEGIES,
    "batch_size": (50, 100, 250),
}
V7_INSTALLS_PER_CHUNK = 8
BASELINE = {"family": "telemetry", "params": {"batch_size": 100, "level": 1}}
M7_REF_NAME = "m7-default-b100-d0-base"
M7_BASELINE = {"family": "v7_frame", "params": {"batch_size": 100, "dictionary_kib": 0, "model": "base", "batching": "fixed"}}   # the frozen M7 default (see BASELINE_REPORT)
SHARED_FIELDS = ("session_id", "app_version", "build_number", "platform", "os_version", "device_class", "locale",
                 "timezone_offset_minutes")
_SAMPLES: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
_V7_META: dict[tuple[str, str, str], list[Any]] = {}
_DIGESTS: dict[tuple[str, int, int], str] = {}


def _v7_timestamp(value: str) -> str | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.microsecond % 1000:
        return None
    return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _source() -> Path:
    path = os.environ.get("FHEL_TELEMETRY_DATASET")
    if not path:
        raise ValueError("FHEL_TELEMETRY_DATASET must point to the authorized local JSONL.gz export")
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file() or source.suffix != ".gz":
        raise ValueError("telemetry dataset must be a local .gz file")
    return source


def _source_sha(source: Path) -> str:
    st = source.stat()
    key = (str(source), st.st_size, st.st_mtime_ns)
    if key in _DIGESTS:
        return _DIGESTS[key]
    h = hashlib.sha256()
    with source.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    _DIGESTS[key] = h.hexdigest()
    return _DIGESTS[key]


def _load(source: Path) -> dict[str, dict[str, list[dict[str, Any]]]]:
    key = str(source)
    if (key, "development") in _SAMPLES:
        return {split: _SAMPLES[(key, split)] for split in ("development", "validation", "held_out") if (key, split) in _SAMPLES}

    raw_events: dict[str, list[dict[str, Any]]] = {}
    raw_seq: dict[str, list[Any]] = {}
    with gzip.open(source, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if not isinstance(row, dict) or not isinstance(row.get("install_id"), str):
                raise ValueError("telemetry export contains a malformed row")
            if not set(FIELDS) <= row.keys() or row.keys() - EXPORT_FIELDS:
                raise ValueError("telemetry export contains missing or unmodeled fields")
            install = row["install_id"]
            bucket = raw_events.get(install)
            if bucket is None:
                bucket = []
                raw_events[install] = bucket
                raw_seq[install] = []
            if len(bucket) < 600:
                bucket.append({name: row[name] for name in FIELDS})
                raw_seq[install].append(row.get("sequence"))
    ordered = sorted(raw_events, key=lambda value: hashlib.sha256(value.encode("utf-8")).digest())
    d, v = round(len(ordered) * .70), round(len(ordered) * .85)
    roles = {install: "development" if i < d else "validation" if i < v else "held_out"
             for i, install in enumerate(ordered)}
    samples: dict[str, dict[str, list[dict[str, Any]]]] = {s: {} for s in ("development", "validation", "held_out")}
    for install, role in roles.items():
        samples[role][install] = raw_events[install]
        _V7_META[(key, role, install)] = raw_seq[install]
    for role, per_install in samples.items():
        _SAMPLES[(key, role)] = per_install
    return samples


def datasets(split: str) -> list[dict[str, Any]]:
    if split not in ("development", "validation", "held_out"):
        raise ValueError("unknown telemetry split")
    source = _source()
    per_install = _load(source)[split]
    digest = _source_sha(source)
    return [{"dataset_id": f"mortris-{split}-{i:03d}", "category": "installation", "data": {
        "role": split, "sample_events": len(rows), "source_sha256": digest, "sample_policy": "first-600-events-per-install/v1"}}
        for i, rows in enumerate(per_install.values()) if rows]


def _envelope(install: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    project = events[0].get("project_id", "puzzle_gravity_test")
    return {"schema_version": 1, "project_id": project, "install_id": install, "sdk": SDK,
            "sent_at_client": SENT_AT}


def _body(install: str, events: list[dict[str, Any]], family: str, params: Mapping[str, Any] | None = None) -> bytes:
    header = _envelope(install, events)
    if family == "telemetry":
        body = {**header, "events": events}
    elif family == "dictionary":
        dictionary: list[str] = []
        indices: dict[str, int] = {}
        rows = []
        for event in events:
            row = []
            for field in FIELDS:
                value = event[field]
                if isinstance(value, str):
                    if value not in indices:
                        indices[value] = len(dictionary)
                        dictionary.append(value)
                    value = {"$string": indices[value]}
                row.append(value)
            rows.append(row)
        body = {**header, "encoding": 1, "dictionary": dictionary, "events": rows}
    elif family == "shared_metadata":
        shared = {field: events[0][field] for field in SHARED_FIELDS
                  if all(event[field] == events[0][field] for event in events)}
        body = {**header, "encoding": 3, "shared": shared,
                "events": [{field: value for field, value in event.items() if field not in shared} for event in events]}
    elif family in ("columnar", "codec_columnar"):
        body = {**header, "encoding": 1, "events": {field: [event[field] for event in events] for field in FIELDS}}
    elif family == "delta_columnar":
        columns = {field: [event[field] for event in events] for field in FIELDS}
        elapsed, previous = [], 0
        for value in columns["session_elapsed_ms"]:
            if value is None:
                elapsed.append(None)
            elif type(value) is int:
                elapsed.append(value - previous)
                previous = value
            else:
                raise ValueError("session_elapsed_ms must contain integers or null")
        columns["session_elapsed_ms"] = elapsed
        body = {**header, "encoding": 2, "events": columns}
    elif family == "composable":
        p = params or {}
        shared = ({field: events[0][field] for field in SHARED_FIELDS
                   if all(event[field] == events[0][field] for event in events)}
                  if p.get("hoist_shared") else {})
        active_fields = [f for f in FIELDS if f not in shared]
        columns = {field: [event[field] for event in events] for field in active_fields}
        if p.get("delta_elapsed") and "session_elapsed_ms" in columns:
            elapsed, previous = [], 0
            for value in columns["session_elapsed_ms"]:
                if value is None:
                    elapsed.append(None)
                elif type(value) is int:
                    elapsed.append(value - previous)
                    previous = value
                else:
                    raise ValueError("session_elapsed_ms must contain integers or null")
            columns["session_elapsed_ms"] = elapsed
        dictionary_comp: list[str] = []
        if p.get("dict_strings"):
            indices_comp: dict[str, int] = {}
            for field in active_fields:
                if field in STRING_FIELDS:
                    col_out: list[Any] = []
                    for value in columns[field]:
                        if isinstance(value, str):
                            idx = indices_comp.get(value)
                            if idx is None:
                                idx = len(dictionary_comp)
                                indices_comp[value] = idx
                                dictionary_comp.append(value)
                            col_out.append(idx)
                        else:
                            col_out.append(value)
                    columns[field] = col_out
        if p.get("layout", "columnar") == "columnar":
            payload_events: Any = columns
        else:
            payload_events = [[columns[field][i] for field in active_fields] for i in range(len(events))]
        body = {**header, "encoding": 4, "shared": shared, "events": payload_events}
        if p.get("dict_strings"):
            body["dictionary"] = dictionary_comp
    else:
        raise ValueError("unknown telemetry encoding family")
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _decode(payload: bytes, family: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    body = json.loads(payload)
    if family == "telemetry":
        return body
    if family == "dictionary":
        dictionary = body.pop("dictionary")
        body.pop("encoding")
        events = []
        for row in body["events"]:
            if len(row) != len(FIELDS):
                raise ValueError("dictionary event field count differs")
            event = {}
            for field, value in zip(FIELDS, row, strict=True):
                if field in STRING_FIELDS and isinstance(value, dict) and set(value) == {"$string"}:
                    value = dictionary[value["$string"]]
                event[field] = value
            events.append(event)
        body["events"] = events
        return body
    if family == "shared_metadata":
        if body.pop("encoding") != 3:
            raise ValueError("shared-metadata encoding version differs")
        shared, rows = body.pop("shared"), body["events"]
        if not isinstance(shared, dict) or set(shared) - set(SHARED_FIELDS) or not isinstance(rows, list):
            raise ValueError("shared metadata is invalid")
        events = []
        for row in rows:
            if not isinstance(row, dict) or set(row) & set(shared) or set(row) | set(shared) != set(FIELDS):
                raise ValueError("shared-metadata event fields differ")
            events.append({field: shared[field] if field in shared else row[field] for field in FIELDS})
        body["events"] = events
        return body
    if family in ("columnar", "delta_columnar", "codec_columnar"):
        encoding = body.pop("encoding")
        columns = body["events"]
        lengths = {len(columns[field]) for field in FIELDS}
        if len(lengths) != 1:
            raise ValueError("column lengths differ")
        if family == "delta_columnar":
            if encoding != 2:
                raise ValueError("delta-columnar encoding version differs")
            previous = 0
            elapsed = []
            for delta in columns["session_elapsed_ms"]:
                if delta is None:
                    elapsed.append(None)
                elif type(delta) is int:
                    previous += delta
                    elapsed.append(previous)
                else:
                    raise ValueError("session elapsed delta must be an integer or null")
            columns["session_elapsed_ms"] = elapsed
        body["events"] = [{field: columns[field][i] for field in FIELDS} for i in range(next(iter(lengths)))]
        return body
    if family == "composable":
        p = params or {}
        if body.pop("encoding") != 4:
            raise ValueError("composable encoding version differs")
        shared = body.pop("shared", {})
        dictionary_comp = body.pop("dictionary", None)
        active_fields = [f for f in FIELDS if f not in shared]
        if p.get("layout", "columnar") == "columnar":
            columns = body["events"]
            n = len(next(iter(columns.values()))) if columns else 0
        else:
            rows = body["events"]
            n = len(rows)
            columns = {field: [rows[i][j] for i in range(n)] for j, field in enumerate(active_fields)}
        if p.get("dict_strings") and dictionary_comp is not None:
            for field in active_fields:
                if field in STRING_FIELDS:
                    columns[field] = [dictionary_comp[v] if type(v) is int else v for v in columns[field]]
        if p.get("delta_elapsed") and "session_elapsed_ms" in columns:
            previous = 0
            elapsed = []
            for delta in columns["session_elapsed_ms"]:
                if delta is None:
                    elapsed.append(None)
                elif type(delta) is int:
                    previous += delta
                    elapsed.append(previous)
                else:
                    raise ValueError("session elapsed delta must be an integer or null")
            columns["session_elapsed_ms"] = elapsed
        body["events"] = [{field: (shared[field] if field in shared else columns[field][i]) for field in FIELDS} for i in range(n)]
        return body
    raise ValueError("unknown telemetry encoding family")


def _compress(body: bytes, codec: str, level: int) -> bytes:
    if codec == "gzip":
        return gzip.compress(body, compresslevel=level, mtime=0)
    if codec == "zlib":
        return zlib.compress(body, level)
    if codec == "bz2":
        return bz2.compress(body, compresslevel=level)
    if codec == "lzma":
        return lzma.compress(body, preset=level)
    raise ValueError("unknown telemetry compression codec")


def _decompress(payload: bytes, codec: str) -> bytes:
    if codec == "gzip":
        return gzip.decompress(payload)
    if codec == "zlib":
        return zlib.decompress(payload)
    if codec == "bz2":
        return bz2.decompress(payload)
    if codec == "lzma":
        return lzma.decompress(payload)
    raise ValueError("unknown telemetry compression codec")


def _v7_parts(segment: list[tuple[dict[str, Any], int]], size: int, batching: str) -> list[list[tuple[dict[str, Any], int]]]:
    """Batch boundaries: fixed-size chunks, or (``session``) chunks that never span a session_id change. Every event lands in exactly one batch, in order."""
    if batching == "fixed":
        return [segment[i:i + size] for i in range(0, len(segment), size)]
    runs: list[list[tuple[dict[str, Any], int]]] = []
    for item in segment:
        if runs and runs[-1][0][0]["session_id"] == item[0]["session_id"]:
            runs[-1].append(item)
        else:
            runs.append([item])
    return [run[i:i + size] for run in runs for i in range(0, len(run), size)]


def _measure_v7(params: Mapping[str, Any], data_sets: list[dict[str, Any]], repeats: int, slow_limit_s: float) -> dict[str, Any]:
    started = time.monotonic()
    if not data_sets or any(d.get("data", {}).get("role") not in ("development", "validation", "held_out") for d in data_sets):
        return {"ok": False, "rejection": "v7_valid_split_required", "rows": []}
    source = str(_source())
    _load(Path(source))
    samples: list[dict[str, Any]] = []
    rows: list[dict[str, int]] = []
    expected_samples = 0
    totals = {key: 0 for key in ("frames", "encoded_events", "fallback_events", "fallback_bytes", "alias_records", "encode_ns", "decode_ns")}
    failure_kinds: dict[str, int] = {}
    catalog_sha256 = dictionary_sha256 = None
    asset_bytes = 0

    def flush() -> dict[str, Any] | None:
        nonlocal catalog_sha256, dictionary_sha256, asset_bytes
        if not samples:
            return None
        limit_s = slow_limit_s if math.isfinite(slow_limit_s) else 120.0
        remaining = limit_s - (time.monotonic() - started)
        if remaining <= 0:
            return {"ok": False, "rejection": f"too_slow:>{slow_limit_s}s", "rows": []}
        try:
            catalog = telemetry_v7.catalog()
        except ValueError as exc:
            return {"ok": False, "rejection": f"v7_measurement_error:{exc}", "rows": []}
        model = params["model"]
        request = {"project_id": catalog["project_id"], "batch_size": params["batch_size"],
                   "dictionary_kib": params["dictionary_kib"], "integer_model": model in ("integer", "both"),
                   "string_model": model in ("string", "both"), "samples": samples}
        try:
            result = telemetry_v7.measure(request, repeats, remaining)
        except ValueError as exc:
            return {"ok": False, "rejection": f"v7_measurement_error:{exc}", "rows": []}
        except (OSError, KeyError, TypeError, MemoryError) as exc:
            return {"ok": False, "rejection": f"v7_measurement_error:{type(exc).__name__}", "rows": []}
        if not result.get("ok"):
            return result
        rows.extend(result["rows"])
        for key in totals:
            totals[key] += result[key]
        for kind, count in result["failure_kinds"].items():
            failure_kinds[kind] = failure_kinds.get(kind, 0) + count
        catalog_sha256, dictionary_sha256 = result["catalog_sha256"], result["dictionary_sha256"]
        asset_bytes = result["asset_bytes"]
        return None

    for dataset in data_sets:
        role = dataset["data"]["role"]
        installs = list(_SAMPLES[(source, role)].items())
        index = int(dataset["dataset_id"].rsplit("-", 1)[1])
        if index >= len(installs):
            return {"ok": False, "rejection": "dataset_manifest_mismatch", "rows": []}
        install, events = installs[index]
        sequences = _V7_META[(source, role, install)]
        if len(sequences) != len(events):
            return {"ok": False, "rejection": "v7_sequence_manifest_mismatch", "rows": []}

        segments: list[list[tuple[dict[str, Any], int]]] = []
        current: list[tuple[dict[str, Any], int]] = []
        previous = None
        for event, sequence in zip(events, sequences, strict=True):
            if type(sequence) is not int or sequence < 1:
                return {"ok": False, "rejection": "v7_sequence_invalid", "rows": []}
            if previous is not None and sequence <= previous:
                segments.append(current)
                current = []
            current.append((event, sequence))
            previous = sequence
        if current:
            segments.append(current)

        try:
            uuid.UUID(install)
            force_fallback = False
        except (ValueError, AttributeError):
            force_fallback = True
        streams = []
        for epoch_index, segment in enumerate(segments):
            epoch = hashlib.sha256(f"fhel-m7-replay/1\0{install}\0{epoch_index}".encode()).digest()[:8].hex()
            batches = []
            for part in _v7_parts(segment, params["batch_size"], params.get("batching", "fixed")):
                raw_events = [event for event, _ in part]
                body = _body(install, raw_events, "telemetry")
                batch_times = [_v7_timestamp(event["occurred_at_client"]) for event in raw_events]
                wire_events = []
                for (event, sequence), wire_time in zip(part, batch_times, strict=True):
                    wire = {key: event[key] for key in FIELDS if key != "event_id"}
                    wire["occurred_at_client"] = wire_time or event["occurred_at_client"]
                    wire["sequence"] = sequence
                    wire_events.append(wire)
                batches.append({"events": wire_events, "input_bytes": len(body),
                                "fallback_bytes": len(gzip.compress(body, compresslevel=1, mtime=0)),
                                "force_fallback": force_fallback or any(value is None for value in batch_times)})
            streams.append({"origin": install, "epoch": epoch, "batches": batches})

        v1_gzip100 = 0
        for start in range(0, len(events), 100):
            body = _body(install, events[start:start + 100], "telemetry")
            v1_gzip100 += len(gzip.compress(body, compresslevel=1, mtime=0))
        samples.append({"origin": install, "streams": streams, "v1_gzip100_bytes": v1_gzip100})
        expected_samples += len(events)
        if len(samples) >= V7_INSTALLS_PER_CHUNK:
            error = flush()
            if error:
                return error
            samples.clear()
    error = flush()
    if error:
        return error
    outputs = [row["output_bytes"] for row in rows]
    inputs = [row["input_bytes"] for row in rows]
    counts = [row["events"] for row in rows]
    v1_gzip100 = [row["v1_gzip100_bytes"] for row in rows]
    total_output, total_events = sum(outputs), sum(counts)
    return {"ok": total_events == expected_samples, "rejection": None,
            "rows": {"output_bytes": outputs, "input_bytes": inputs, "events": counts},
            "geo_ratio": geo_mean(out / size for out, size in zip(outputs, inputs, strict=True) if size),
            "payload_bytes_per_event": total_output / max(1, total_events),
            "v1_gzip100_bytes_per_event": sum(v1_gzip100) / max(1, total_events),
            "weighted_reduction_vs_v1_gzip100": 1 - total_output / max(1, sum(v1_gzip100)),
            "fallback_events": totals["fallback_events"], "fallback_bytes": totals["fallback_bytes"],
            "fallback_reasons": failure_kinds,
            "encoded_events": totals["encoded_events"], "frames": totals["frames"],
            "alias_records": totals["alias_records"], "asset_bytes": asset_bytes,
            "catalog_sha256": catalog_sha256, "dictionary_sha256": dictionary_sha256,
            "compress_ns": totals["encode_ns"] // repeats, "decompress_ns": totals["decode_ns"] // repeats}


def _measure_code_codec(params: Mapping[str, Any], data_sets: list[dict[str, Any]], repeats: int, slow_limit_s: float) -> dict[str, Any]:
    source = str(_source())
    _load(Path(source))
    batch_items: list[dict[str, Any]] = []
    counts: list[int] = []
    comp_params = {"hoist_shared": True, "delta_elapsed": True, "dict_strings": True, "layout": "columnar"}
    for d in data_sets:
        role = d["data"]["role"]
        installs = list(_SAMPLES[(source, role)].items())
        index = int(d["dataset_id"].rsplit("-", 1)[1])
        if index >= len(installs):
            return {"ok": False, "rejection": "dataset_manifest_mismatch", "rows": []}
        install, events = installs[index]
        raw_input_bytes = 0
        frames: list[bytes] = []
        for start in range(0, len(events), params["batch_size"]):
            batch = events[start:start + params["batch_size"]]
            raw_input_bytes += len(_body(install, batch, "telemetry"))
            frame = _body(install, batch, "composable", comp_params)
            if _decode(frame, "composable", comp_params) != {**_envelope(install, batch), "events": batch}:
                return {"ok": False, "rejection": "round_trip_mismatch", "rows": []}
            frames.append(frame)
        raw_frame_bytes = b"\n".join(frames)
        batch_items.append({
            "id": str(d["dataset_id"]),
            "raw_bytes": raw_input_bytes,
            "raw_frames": raw_frame_bytes,
        })
        counts.append(len(events))
    res = telemetry_code.execute_sandboxed_batches(
        language=str(params["language"]),
        strategy=str(params["strategy"]),
        batch_items=batch_items,
        repeats=repeats,
        slow_limit_s=slow_limit_s,
    )
    if not res.get("ok"):
        return {"ok": False, "rejection": str(res.get("rejection", "code_codec_failed")), "rows": []}
    rows = res["rows"]
    outputs = [int(r["output_bytes"]) for r in rows]
    inputs = [int(r["raw_bytes"]) for r in rows]
    total_output, total_events = sum(outputs), sum(counts)
    compress_ns = sum(sum(int(x) for x in r.get("compress_ns", [0])) for r in rows) // max(1, repeats)
    decompress_ns = sum(sum(int(x) for x in r.get("decompress_ns", [0])) for r in rows) // max(1, repeats)
    return {
        "ok": True,
        "rejection": None,
        "rows": {"output_bytes": outputs, "input_bytes": inputs, "events": counts},
        "geo_ratio": geo_mean(out / size for out, size in zip(outputs, inputs, strict=True) if size),
        "payload_bytes_per_event": total_output / max(1, total_events),
        "compress_ns": compress_ns,
        "decompress_ns": decompress_ns,
        "sandbox_backend": "macos_seatbelt",
        "tier1_receipt_sha256": res.get("tier1_receipt_sha256"),
        "bundle_sha256": res.get("bundle_sha256"),
        "language": res.get("language"),
    }


def _measure(spec: Mapping[str, Any], data_sets: list[dict[str, Any]], repeats: int, slow_limit_s: float) -> dict[str, Any]:
    p = spec["params"]
    family = spec["family"]
    if family == "v7_frame":
        return _measure_v7(p, data_sets, repeats, slow_limit_s)
    if family == "code_codec":
        return _measure_code_codec(p, data_sets, repeats, slow_limit_s)
    codec = p.get("codec", "gzip")
    source = str(_source())
    _load(Path(source))
    rows: list[dict[str, int]] = []
    started = time.perf_counter()
    compress_ns = decompress_ns = 0
    all_bytes = raw_bytes = 0
    for d in data_sets:
        sample = d["data"]
        key = (source, sample["role"])
        installs = list(_SAMPLES[key].items())
        index = int(d["dataset_id"].rsplit("-", 1)[1])
        if index >= len(installs):
            return {"ok": False, "rejection": "dataset_manifest_mismatch", "rows": []}
        install, events = installs[index]
        out_n = input_n = 0
        for _ in range(repeats):
            one_out = one_in = 0
            for start in range(0, len(events), p["batch_size"]):
                batch = events[start:start + p["batch_size"]]
                input_body = _body(install, batch, "telemetry") if family != "telemetry" else None
                before = time.perf_counter_ns()
                body = _body(install, batch, family, p)
                serialized = _compress(body, codec, p["level"])
                after = time.perf_counter_ns()
                restored = _decompress(serialized, codec)
                reconstructed = _decode(restored, family, p)
                end = time.perf_counter_ns()
                expected = {**_envelope(install, batch), "events": batch}
                if reconstructed != expected:
                    return {"ok": False, "rejection": "round_trip_mismatch", "rows": []}
                compress_ns += after - before
                decompress_ns += end - after
                one_out += len(serialized)
                one_in += len(body) if input_body is None else len(input_body)
            out_n, input_n = one_out, one_in
            if time.perf_counter() - started > slow_limit_s:
                return {"ok": False, "rejection": f"too_slow:>{slow_limit_s}s", "rows": rows}
        rows.append({"output_bytes": out_n, "input_bytes": input_n, "events": len(events)})
        all_bytes += out_n
        raw_bytes += input_n
    return {"ok": True, "rejection": None, "rows": {k: [r[k] for r in rows] for k in ("output_bytes", "input_bytes", "events")},
            "geo_ratio": geo_mean(r["output_bytes"] / r["input_bytes"] for r in rows if r["input_bytes"]),
            "payload_bytes_per_event": all_bytes / max(1, sum(r["events"] for r in rows)),
            "compress_ns": compress_ns // repeats, "decompress_ns": decompress_ns // repeats}


class TelemetryProblem(Problem):
    id = "telemetry_payload"
    version = "7"
    protocol = 3
    independent_roles_unavailable = {
        "fresh": "the validation cohort was exposed in WP-AUT-04; no untouched MORTRIS cohort is available",
        "confirmation": "the held-out cohort was exposed in WP-AUT-04; no sealed MORTRIS confirmation cohort exists",
    }
    evaluators = (TELEMETRY,)
    metrics = {"geo_ratio": "geometric mean of compressed payload bytes / V1 JSON body bytes per installation (lower is better)",
               "time_ratio": "encoding CPU time relative to V1 gzip-1, batch-100 (lower is better)",
               "decompress_time_ratio": "decode CPU time relative to V1 gzip-1, batch-100 (lower is better)"}

    def default_config(self) -> dict[str, Any]:
        return {"evaluator": TELEMETRY, "search_space": {"telemetry": "all"}, "constraints": {
            "reference": "v1-gzip1-b100", "max_compress_ratio": 4.0, "max_decompress_ratio": 4.0}, "time_constraint": None}

    def validate_config(self, cfg: Mapping[str, Any]) -> None:
        c = cfg["constraints"]
        if (cfg["evaluator"] != TELEMETRY or not isinstance(c, Mapping)
                or set(c) != {"reference", "max_compress_ratio", "max_decompress_ratio"}
                or c["reference"] != "v1-gzip1-b100"
                or any(type(c[k]) not in (int, float) or not 0 < c[k] <= 100 for k in ("max_compress_ratio", "max_decompress_ratio"))
                or cfg["time_constraint"] is not None or cfg["faults"] or cfg["synthetic_sleep_s"]):
            raise ValueError("telemetry requires the trusted evaluator, fixed V1 reference, and bounded cost ratios")
        self.make_space(cfg["search_space"])
        _source()

    def constraints(self, cfg: Mapping[str, Any]) -> dict[str, Any]:
        return dict(cfg["constraints"])

    def reference(self, cfg: Mapping[str, Any]) -> str:
        return cfg["constraints"]["reference"]

    def make_space(self, search_space: Mapping[str, Any]) -> DomainSpace:
        return DomainSpace(search_space, DOMAINS)

    def baselines(self) -> dict[str, dict[str, Any]]:
        return {"v1-gzip1-b100": BASELINE}

    def parse_candidate(self, obj: Any, space: Any = None) -> dict[str, Any]:
        return parse_in(DOMAINS, None, obj, space)

    def source_modules(self) -> list[Any]:
        return [campaign_search, sys.modules[__name__], telemetry_v7, telemetry_code]

    def identity_bytes(self) -> bytes:
        return b"mortris-telemetry-sample/7\0" + telemetry_v7.asset_identity()

    def datasets(self, split: str) -> list[dict[str, Any]]:
        return datasets(split)

    def independent_datasets(self, role: str) -> list[dict[str, Any]]:
        if role in self.independent_roles_unavailable:
            raise ValueError(self.independent_roles_unavailable[role])
        if role == "fresh":
            return datasets("validation")
        if role == "confirmation":
            return datasets("held_out")
        raise ValueError(f"unknown independent telemetry role: {role!r}")

    def dataset_provenance(self) -> dict[str, Any]:
        return {"generator": "fhel-mortris-telemetry/6", "partition": "installation-disjoint SHA-256 order: 70/15/15",
                "sample": "first 600 events per installation; V1 client fields plus sequence sidecar for M7 replay",
                "source_sha256": _source_sha(_source()), "v7_assets_sha256": hashlib.sha256(telemetry_v7.asset_identity()).hexdigest(),
                "reference_baseline": "v1-gzip1-b100",
                "m7_comparison": "not tested: candidates are measured against the reconstructed V1 baseline; v7_frame is itself a candidate family, not the reference",
                "held_out_status": "EXPOSED: the held_out cohort's aggregate results for nine candidates were printed in the WP-AUT-04 demonstration (docs/DATA_EXPOSURE_LEDGER.md); "
                                   "it is a descriptive cohort, not an uncontaminated confirmation set. No sealed confirmation cohort exists."}

    def environment(self) -> dict[str, str]:
        return {"python": platform.python_version(), "implementation": platform.python_implementation(), "platform": platform.platform()}

    def measure_reference(self, request: Mapping[str, Any], data_sets: list[dict[str, Any]]) -> dict[str, Any]:
        return _measure(BASELINE, data_sets, request["repeats"], request["slow_limit_s"])

    def measure(self, spec: Mapping[str, Any], data_sets: list[dict[str, Any]], request: Mapping[str, Any]) -> dict[str, Any]:
        try:
            return _measure(spec, data_sets, request["repeats"], request["slow_limit_s"])
        except (OSError, ValueError, KeyError, TypeError, EOFError, gzip.BadGzipFile, MemoryError, lzma.LZMAError) as exc:
            return {"ok": False, "rejection": f"telemetry_error:{type(exc).__name__}", "rows": []}

    def finish(self, result: dict[str, Any], ref: dict[str, Any] | None, request: Mapping[str, Any]) -> None:
        if result.get("ok") and ref and ref.get("ok"):
            result["time_ratio"] = result["compress_ns"] / max(1, ref["compress_ns"])
            result["decompress_time_ratio"] = result["decompress_ns"] / max(1, ref["decompress_ns"])
        else:
            result["time_ratio"] = result["decompress_time_ratio"] = math.inf

    def reference_summary(self, ref: dict[str, Any]) -> dict[str, Any]:
        return {k: ref[k] for k in ("geo_ratio", "payload_bytes_per_event", "compress_ns", "decompress_ns")}

    def feasible(self, result: Mapping[str, Any], constraints: Mapping[str, Any]) -> tuple[bool, str | None]:
        ok = (bool(result.get("ok")) and result["time_ratio"] <= constraints["max_compress_ratio"]
              and result["decompress_time_ratio"] <= constraints["max_decompress_ratio"])
        return ok, None if ok else "time_constraint"

    def per_dataset(self, rows: Mapping[str, Any], manifest: list[dict[str, Any]]) -> dict[str, float] | None:
        return {m["dataset_id"]: round(o / n, 6) for m, o, n in zip(manifest, rows["output_bytes"], rows["input_bytes"], strict=True)}

    def describe(self) -> dict[str, Any]:
        return {"primary": "compressed payload bytes / reconstructed V1 JSON body bytes", "secondary": "encode/decode CPU time ratio vs the reference baseline",
                "fixed": "trusted replay of the first 600 events per installation; the frozen M7 C# encoder, Go decoder, catalog and dictionaries are not searched",
                "algorithm": "steady-state genetic search over typed parameters of allowlisted families, hash deduplication, development-only selection",
                "fitness": "geometric-mean payload bytes / V1 JSON body bytes on development installations (lower is better), feasible within the CPU-ratio limits",
                "selection": "development only (selection_mode=development_only); no independent validation or confirmation cohort exists",
                "best_note": "best development configuration of an allowlisted data-only family; exploratory, not independent confirmation",
                "exhausted_hint": "The narrowed space is fully measured; refine or change the domain rather than repeating it.",
                "dataset_hint": "development-only evidence on the exposed MORTRIS export",
                "candidate": "data-only V1 layouts or the frozen MORTRIS M7 frame encoder with bounded parameters", "limitations": [
                    "Reconstructed payload bodies, not packet capture or network/TLS measurements.",
                    "First 600 events per installation; full export profiling is separate evidence.",
                    "Host Python timing does not predict Unity device CPU, memory, or battery.",
                    "M7 timing uses the frozen C# encoder and Go decoder; setup and HTTP/TLS are excluded.",
                    "Non-UUID origins and events rejected by M7 use measured V1 gzip fallback; catalog/dictionary setup bytes are reported separately."]}


class TelemetryM7Problem(TelemetryProblem):
    """Same trusted data, replay and measurement code as ``TelemetryProblem`` but the reference is the frozen M7 default (batch 100, no dictionary,
    base model), not reconstructed V1 gzip: ``dev_gain`` is the geo-ratio saved relative to M7, and the CPU ratios are relative to M7's own encode/decode."""
    id = "telemetry_m7_payload"
    version = "1"
    evaluators = (TELEMETRY_M7,)
    metrics = {"geo_ratio": "geometric mean of M7 frame payload bytes / V1 JSON body bytes per installation (lower is better)",
               "time_ratio": "M7 encode CPU time relative to the frozen M7 default (lower is better)",
               "decompress_time_ratio": "independent Go decode CPU time relative to the frozen M7 default (lower is better)"}

    def default_config(self) -> dict[str, Any]:
        return {"evaluator": TELEMETRY_M7, "search_space": {"v7_frame": "all"}, "constraints": {
            "reference": M7_REF_NAME, "max_compress_ratio": 4.0, "max_decompress_ratio": 4.0}, "time_constraint": None}

    def validate_config(self, cfg: Mapping[str, Any]) -> None:
        c = cfg["constraints"]
        if (cfg["evaluator"] != TELEMETRY_M7 or not isinstance(c, Mapping)
                or set(c) != {"reference", "max_compress_ratio", "max_decompress_ratio"} or c["reference"] != M7_REF_NAME
                or any(type(c[k]) not in (int, float) or not 0 < c[k] <= 100 for k in ("max_compress_ratio", "max_decompress_ratio"))
                or cfg["time_constraint"] is not None or cfg["faults"] or cfg["synthetic_sleep_s"]):
            raise ValueError("telemetry-m7 requires the trusted M7 evaluator, the frozen M7 default reference, and bounded cost ratios")
        self.make_space(cfg["search_space"])
        _source()

    def make_space(self, search_space: Mapping[str, Any]) -> DomainSpace:
        if set(search_space) != {"v7_frame"}:
            raise ValueError("the M7-reference problem searches only the v7_frame family")
        return DomainSpace(search_space, DOMAINS)

    def baselines(self) -> dict[str, dict[str, Any]]:
        return {M7_REF_NAME: M7_BASELINE}

    def identity_bytes(self) -> bytes:
        return b"mortris-telemetry-m7-reference/1\0" + telemetry_v7.asset_identity()

    def dataset_provenance(self) -> dict[str, Any]:
        return {**super().dataset_provenance(), "reference_baseline": M7_REF_NAME,
                "m7_comparison": "tested: the reference is the frozen M7 default (batch 100, dictionary 0 KiB, base model) measured on the same events in the same run"}

    def measure_reference(self, request: Mapping[str, Any], data_sets: list[dict[str, Any]]) -> dict[str, Any]:
        return _measure(M7_BASELINE, data_sets, request["repeats"], request["slow_limit_s"])

    def finish(self, result: dict[str, Any], ref: dict[str, Any] | None, request: Mapping[str, Any]) -> None:
        super().finish(result, ref, request)
        if result.get("ok") and ref and ref.get("ok"):
            result["bytes_vs_m7"] = result["payload_bytes_per_event"] / max(1e-9, ref["payload_bytes_per_event"])
            result["ref_payload_bytes_per_event"] = ref["payload_bytes_per_event"]
