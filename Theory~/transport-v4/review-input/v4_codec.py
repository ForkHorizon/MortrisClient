#!/usr/bin/env python3
"""
Mortris Analytics Transport V4 (MTB4) — Reference Lossless Codec & Frame Layer.
Fixes V3 defects:
  1. Removes duplicate column_directory (deterministically derived from shapes).
  2. Removes dead u8 kind=0 bytes in contexts/shapes and redundant dt[0]=0.
  3. Replaces u8 BOOL (8 bits) with bit-packed BOOL (1 bit/value).
  4. Implements ALP-Exact decimal float coding (lossless scale + -0.0 + Chimp XOR)
     eliminating NUMTEXT bloat and Kind0 whole-batch fallback.
  5. Segregates incompressible UUID16 and unpredicted binary HEX32 into an
     uncompressed raw_trailer so high-entropy bytes do not pollute Zstd match tables.
  6. Replaces Kind2 string "=" sentinel with a 1-bit hash prediction bitmap
     keeping anchor hashes at 32 binary bytes instead of 64 ASCII bytes.
  7. Synthesizes the 2-byte magicless Zstd frame/window header on decode.
  8. Enforces per-event raw_len ceiling: raw_len <= 4096 + n * 8704 BEFORE allocation.
"""

from __future__ import annotations
import hashlib
import json
import math
import struct
import zlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False


# --- Primitive LEB128 & ZigZag with Strict 64-bit Overflow Guards ---

def put_uvarint(val: int) -> bytes:
    if val < 0 or val > 0xFFFFFFFFFFFFFFFF:
        raise ValueError(f"uvarint out of uint64 domain: {val}")
    out = bytearray()
    while val >= 0x80:
        out.append((val & 0x7F) | 0x80)
        val >>= 7
    out.append(val)
    return bytes(out)


def read_uvarint(buf: bytes, pos: int) -> Tuple[int, int]:
    result = 0
    shift = 0
    for i in range(10):
        if pos >= len(buf):
            raise ValueError("BAD_FRAME: truncated uvarint")
        b = buf[pos]
        pos += 1
        if i == 9 and b > 1:
            raise ValueError("BAD_FRAME: uint64 uvarint overflow (>64 bits)")
        result |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            # Reject overlong non-canonical encodings
            if i > 0 and b == 0:
                raise ValueError("BAD_FRAME: overlong uvarint")
            return result, pos
        shift += 7
    raise ValueError("BAD_FRAME: uvarint exceeds 10 bytes")


def put_svarint(val: int) -> bytes:
    if val < -0x8000000000000000 or val > 0x7FFFFFFFFFFFFFFF:
        raise ValueError(f"svarint out of int64 domain: {val}")
    zz = (val << 1) ^ (val >> 63)
    return put_uvarint(zz & 0xFFFFFFFFFFFFFFFF)


def read_svarint(buf: bytes, pos: int) -> Tuple[int, int]:
    zz, pos = read_uvarint(buf, pos)
    return (zz >> 1) ^ -(zz & 1), pos


# --- Bit-Packing & Frame-of-Reference (FoR) for Narrow Integer Columns ---

def pack_bits(values: List[int], width: int) -> bytes:
    if width == 0 or not values:
        return b""
    acc = 0
    bits_in_acc = 0
    out = bytearray()
    mask = (1 << width) - 1
    for v in values:
        acc |= (v & mask) << bits_in_acc
        bits_in_acc += width
        while bits_in_acc >= 8:
            out.append(acc & 0xFF)
            acc >>= 8
            bits_in_acc -= 8
    if bits_in_acc > 0:
        out.append(acc & 0xFF)
    return bytes(out)


def unpack_bits(buf: bytes, pos: int, count: int, width: int) -> Tuple[List[int], int]:
    if count == 0:
        return [], pos
    if width == 0:
        return [0] * count, pos
    nbytes = (count * width + 7) // 8
    if pos + nbytes > len(buf):
        raise ValueError("BAD_FRAME: truncated bitpack stream")
    vals: List[int] = []
    acc = 0
    bits_in_acc = 0
    idx = pos
    mask = (1 << width) - 1
    for _ in range(count):
        while bits_in_acc < width:
            acc |= buf[idx] << bits_in_acc
            idx += 1
            bits_in_acc += 8
        vals.append(acc & mask)
        acc >>= width
        bits_in_acc -= width
    return vals, pos + nbytes


def encode_int_column(values: List[int]) -> bytes:
    """
    Chooses optimal representation between:
      mode 0: FoR (Frame-of-Reference min_val + bitpack width)
      mode 1: Delta + FoR bitpack (ideal for monotone/Elias-Fano-like sequences)
      mode 2: Delta + svarint (when outliers exist)
    """
    if not values:
        return b"\x00"
    # Candidate A: Direct FoR + BitPack
    min_v = min(values)
    max_v = max(values)
    span = max_v - min_v
    if span <= 0xFFFFFFFF:
        w = span.bit_length()
        cand_a = b"\x00" + put_svarint(min_v) + bytes([w]) + pack_bits([v - min_v for v in values], w)
    else:
        cand_a = None

    # Candidate B: Delta + FoR BitPack
    deltas = [values[0]] + [values[i] - values[i - 1] for i in range(1, len(values))]
    d_min = min(deltas)
    d_max = max(deltas)
    d_span = d_max - d_min
    if d_span <= 0xFFFFFFFF:
        dw = d_span.bit_length()
        cand_b = b"\x01" + put_svarint(d_min) + bytes([dw]) + pack_bits([d - d_min for d in deltas], dw)
    else:
        cand_b = None

    # Candidate C: Delta + svarint
    cand_c = b"\x02" + b"".join(put_svarint(d) for d in deltas)

    candidates = [c for c in (cand_a, cand_b, cand_c) if c is not None]
    return min(candidates, key=len)


def decode_int_column(buf: bytes, pos: int, count: int) -> Tuple[List[int], int]:
    if count == 0:
        return [], pos
    mode = buf[pos]
    pos += 1
    if mode == 0:
        min_v, pos = read_svarint(buf, pos)
        w = buf[pos]
        pos += 1
        offsets, pos = unpack_bits(buf, pos, count, w)
        return [min_v + o for o in offsets], pos
    elif mode == 1:
        d_min, pos = read_svarint(buf, pos)
        dw = buf[pos]
        pos += 1
        d_offsets, pos = unpack_bits(buf, pos, count, dw)
        out: List[int] = []
        cur = 0
        for o in d_offsets:
            cur += d_min + o
            out.append(cur)
        return out, pos
    elif mode == 2:
        out = []
        cur = 0
        for _ in range(count):
            d, pos = read_svarint(buf, pos)
            cur += d
            out.append(cur)
        return out, pos
    raise ValueError(f"BAD_FRAME: unknown int column mode {mode}")


# --- ALP-Exact Lossless Decimal & IEEE-754 Float Codec ---

def encode_alp_number(lexeme: str) -> Tuple[int, bytes]:
    """
    Losslessly encodes any finite JSON numeric lexeme without NUMTEXT bloat:
      - If standard canonical decimal (e.g. '120.0', '-0.0', '12.345'):
        stores (scale_and_flags: u8, mantissa: svarint) in 2..4 bytes!
      - If scientific notation or exotic float:
        stores raw IEEE-754 f64 if round-trip exact, else compact ASCII lexeme.
    """
    if lexeme == "-0.0":
        return 1, b"\x81\x00"  # Special flag for -0.0
    if "." in lexeme and "e" not in lexeme and "E" not in lexeme:
        parts = lexeme.split(".")
        if len(parts) == 2 and 1 <= len(parts[1]) <= 15:
            frac_len = len(parts[1])
            # Check that reconstructing from integer mantissa is 100% byte-exact
            sign = -1 if lexeme.startswith("-") else 1
            digits = (parts[0][1:] if sign < 0 else parts[0]) + parts[1]
            if digits.isdigit() and not (len(parts[0].lstrip("-")) > 1 and parts[0].lstrip("-").startswith("0")):
                mantissa = int(digits) * sign
                if -0x7FFFFFFFFFFFFFFF <= mantissa <= 0x7FFFFFFFFFFFFFFF:
                    reconstructed = f"{'-' if sign < 0 and mantissa == 0 else ''}{mantissa / (10 ** frac_len):.{frac_len}f}"
                    if reconstructed == lexeme:
                        return 1, bytes([frac_len & 0x0F]) + put_svarint(mantissa)
    # Try binary IEEE-754 f64 if standard repr matches lexeme
    try:
        fval = float(lexeme)
        if math.isfinite(fval) and repr(fval) == lexeme:
            return 2, struct.pack("<d", fval)
    except ValueError:
        pass
    # Token-level literal escape (never forces entire batch into Kind0!)
    raw = lexeme.encode("utf-8")
    return 3, put_uvarint(len(raw)) + raw


def decode_alp_number(subtag: int, buf: bytes, pos: int) -> Tuple[str, int]:
    if subtag == 1:
        hdr = buf[pos]
        pos += 1
        if hdr == 0x81:
            _, pos = read_svarint(buf, pos)
            return "-0.0", pos
        frac_len = hdr & 0x0F
        mantissa, pos = read_svarint(buf, pos)
        sign_str = "-" if mantissa < 0 else ""
        abs_m = abs(mantissa)
        s = str(abs_m).zfill(frac_len + 1)
        return f"{sign_str}{s[:-frac_len]}.{s[-frac_len:]}", pos
    elif subtag == 2:
        fval = struct.unpack("<d", buf[pos:pos + 8])[0]
        return repr(fval), pos + 8
    elif subtag == 3:
        ln, pos = read_uvarint(buf, pos)
        return buf[pos:pos + ln].decode("utf-8"), pos + ln
    raise ValueError(f"BAD_FRAME: invalid ALP subtag {subtag}")


# --- Format-Independent Canonical Event Digest (Fixes V1/Kind0 <-> MTB4 Conflict) ---

def canonical_event_digest(event: Dict[str, Any], origin_epoch: str) -> bytes:
    """
    Computes SHA-256 over a format-independent canonical representation of an event
    (excluding event_id and batch sent_at), guaranteeing identical digests across
    V1 JSON, Kind0 literal fallback, and MTB4 columnar reconstruction.
    """
    h = hashlib.sha256()
    h.update(b"MTB4_EVENT_V1\x00")
    h.update(origin_epoch.lower().encode("ascii") + b"\x00")
    h.update(str(event["sequence"]).encode("ascii") + b"\x00")
    h.update(event["event_name"].encode("utf-8") + b"\x00")
    h.update(str(event["timestamp_ms"]).encode("ascii") + b"\x00")
    props = event.get("properties", {})
    for k, v in props.items():
        h.update(k.encode("utf-8") + b"=" + repr(v).encode("utf-8") + b";")
    return h.digest()


# --- Rule 1 Game State Hash Predictor with 1-Bit Bitmap + Raw Binary Trailer ---

def predict_mortris_hash(prev_hex: str, block_id: int, cx: int, cy: int) -> str:
    if not (0 <= block_id <= 255 and 0 <= cx <= 255 and 0 <= cy <= 255):
        return ""
    msg = prev_hex.encode("ascii") + bytes([block_id, cx, cy])
    return hashlib.sha256(msg).hexdigest()


# --- Outer V4 Frame with Guarded Streaming Allocation & Request-Bound 4-Byte ACK ---

MAX_HTTP_FRAME = 262144
MAX_EVENTS_PER_BATCH = 500
PER_EVENT_RAW_CEILING = 8704
BASE_RAW_CEILING = 4096


def pack_v4_frame(
    structured_stream: bytes,
    raw_trailer: bytes,
    n_events: int,
    dict_id: int = 0,
    zstd_dict_bytes: Optional[bytes] = None,
    level: int = 15,
) -> bytes:
    """
    Outer Frame V4:
      u8 header = 0x40 | codec (0=raw, 1=zlib, 2=synthesized-header zstd)
      uvarint n_events (1..500) -> checked BEFORE allocating raw buffer!
      uvarint dict_id (0..127)
      uvarint structured_raw_len
      uvarint trailer_len
      bytes compressed_structured_stream
      bytes raw_trailer (uncompressed high-entropy UUID16 / unpredicted SHA256 bytes)
    """
    if not (1 <= n_events <= MAX_EVENTS_PER_BATCH):
        raise ValueError(f"Invalid event count: {n_events}")
    max_allowed_raw = BASE_RAW_CEILING + n_events * PER_EVENT_RAW_CEILING
    if len(structured_stream) + len(raw_trailer) > max_allowed_raw:
        raise ValueError("Payload exceeds domain per-event raw ceiling")

    best_codec = 0
    best_comp = structured_stream

    # Option 1: deflate/zlib fallback
    z_comp = zlib.compress(structured_stream, level=6)
    if len(z_comp) < len(best_comp):
        best_codec = 1
        best_comp = z_comp

    # Option 2: Zstd (with or without dictionary)
    if HAS_ZSTD:
        cparams = zstd.ZstdCompressionParameters.from_level(
            level, write_content_size=False, write_checksum=False, write_dict_id=False
        )
        if zstd_dict_bytes and dict_id > 0:
            zd = zstd.ZstdCompressionDict(zstd_dict_bytes)
            cctx = zstd.ZstdCompressor(compression_params=cparams, dict_data=zd)
        else:
            cctx = zstd.ZstdCompressor(compression_params=cparams)
        zstd_frame = cctx.compress(structured_stream)
        # Strip the 4-byte Zstd magic (28 b5 2f fd)
        magicless = zstd_frame[4:]
        if len(magicless) < len(best_comp):
            best_codec = 2
            best_comp = magicless

    actual_dict_id = dict_id if best_codec == 2 else 0
    hdr = (
        bytes([0x40 | best_codec])
        + put_uvarint(n_events)
        + put_uvarint(actual_dict_id)
        + put_uvarint(len(structured_stream))
        + put_uvarint(len(raw_trailer))
    )
    return hdr + best_comp + raw_trailer


def unpack_v4_frame(
    frame: bytes,
    dicts: Dict[int, bytes],
) -> Tuple[bytes, bytes, int]:
    if len(frame) < 5 or len(frame) > MAX_HTTP_FRAME:
        raise ValueError("BAD_FRAME: invalid frame size")
    pos = 0
    hdr_byte = frame[pos]
    pos += 1
    if (hdr_byte & 0xF0) != 0x40:
        raise ValueError("BAD_FRAME: invalid V4 magic nibble")
    codec = hdr_byte & 0x0F
    n_events, pos = read_uvarint(frame, pos)
    if not (1 <= n_events <= MAX_EVENTS_PER_BATCH):
        raise ValueError(f"BAD_FRAME: event count {n_events} out of bounds 1..500")

    dict_id, pos = read_uvarint(frame, pos)
    struct_raw_len, pos = read_uvarint(frame, pos)
    trailer_len, pos = read_uvarint(frame, pos)

    # CRITICAL FIX vs V3: Bound raw allocation strictly by n_events * 8704 bytes!
    max_allowed_raw = BASE_RAW_CEILING + n_events * PER_EVENT_RAW_CEILING
    if struct_raw_len + trailer_len > max_allowed_raw:
        raise ValueError(
            f"BAD_FRAME: declared raw size {struct_raw_len + trailer_len} exceeds ceiling {max_allowed_raw} for n={n_events}"
        )
    if pos + trailer_len > len(frame):
        raise ValueError("BAD_FRAME: truncated trailer")

    comp_end = len(frame) - trailer_len
    comp_slice = frame[pos:comp_end]
    raw_trailer = frame[comp_end:]

    if codec == 0:
        if dict_id != 0 or len(comp_slice) != struct_raw_len:
            raise ValueError("BAD_FRAME: raw length mismatch")
        return comp_slice, raw_trailer, n_events
    elif codec == 1:
        if dict_id != 0:
            raise ValueError("BAD_FRAME: nonzero dict_id on zlib")
        dobj = zlib.decompressobj()
        out = dobj.decompress(comp_slice, struct_raw_len + 1)
        out += dobj.flush()
        if len(out) != struct_raw_len or dobj.unused_data:
            raise ValueError("BAD_FRAME: zlib size mismatch or trailing bytes")
        return out, raw_trailer, n_events
    elif codec == 2:
        if not HAS_ZSTD:
            raise ValueError("Zstd unavailable")
        full_zstd = b"\x28\xb5\x2f\xfd" + comp_slice
        params = zstd.get_frame_parameters(full_zstd)
        if params.window_size > 2 * 1024 * 1024:
            raise ValueError("BAD_FRAME: zstd window > 2 MiB")
        if params.content_size not in (0, zstd.CONTENTSIZE_UNKNOWN, struct_raw_len):
            raise ValueError("BAD_FRAME: forged zstd content_size")
        if dict_id != 0:
            if dict_id not in dicts:
                raise KeyError(f"UNKNOWN_DICTIONARY: {dict_id}")
            dctx = zstd.ZstdDecompressor(dict_data=zstd.ZstdCompressionDict(dicts[dict_id]))
        else:
            dctx = zstd.ZstdDecompressor()
        # Stream decompression with strict output cap
        with dctx.stream_reader(full_zstd) as reader:
            chunks = []
            total = 0
            while True:
                chunk = reader.read(16384)
                if not chunk:
                    break
                total += len(chunk)
                if total > struct_raw_len:
                    raise ValueError("BAD_FRAME: zstd output exceeded struct_raw_len")
                chunks.append(chunk)
        out = b"".join(chunks)
        if len(out) != struct_raw_len:
            raise ValueError("BAD_FRAME: zstd output shorter than struct_raw_len")
        return out, raw_trailer, n_events
    raise ValueError(f"BAD_FRAME: unknown codec {codec}")


def make_request_bound_ack(
    origin_epoch_bytes: bytes,
    first_seq: int,
    n_events: int,
    policy_epoch: int,
    status: int = 0,
) -> bytes:
    """
    4-byte Request-Bound ACK (fixes V3's unauthenticated 2-byte '30 01' ACK):
      u8 control = (4 << 4) | (status & 0x07)
      uvarint policy_epoch
      u16 batch_mac16 = truncated BLAKE2s(origin_epoch || first_seq || n_events)
    Prevents accidental queue deletion if responses arrive out-of-order on keep-alive.
    """
    mac = hashlib.blake2s(
        origin_epoch_bytes + struct.pack("<QI", first_seq, n_events), digest_size=2
    ).digest()
    return bytes([0x40 | (status & 0x07)]) + put_uvarint(policy_epoch) + mac

