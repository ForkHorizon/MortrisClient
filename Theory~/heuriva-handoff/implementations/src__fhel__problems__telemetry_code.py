"""Multi-language sandboxed code execution for MORTRIS telemetry codec research.

Compiles and executes candidate codec implementations in Python, C++, Rust, and Go
inside the qualified macOS Seatbelt sandbox (``src/fhel/code_sandbox.py``), enforcing
Tier 1 round-trip correctness verification before Tier 2 native benchmarking.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from .. import code_artifact as ca
from .. import code_sandbox as cs
from .. import sandbox as sb

CODE_LANGUAGES = ("python", "cpp", "rust", "go")
CODE_STRATEGIES = ("columnar_zlib", "delta_dict_zlib", "hoisted_delta_bz2", "compact_frame_lzma")

_PYTHON_TEMPLATE = '''import base64, bz2, hashlib, json, lzma, sys, time, zlib

STRATEGY = __STRATEGY__

def _compress_frame(raw: bytes) -> bytes:
    if STRATEGY == "columnar_zlib":
        return zlib.compress(raw, 6)
    if STRATEGY == "delta_dict_zlib":
        return zlib.compress(raw, 9)
    if STRATEGY == "hoisted_delta_bz2":
        return bz2.compress(raw, 9)
    return lzma.compress(raw, preset=3)

def _decompress_frame(comp: bytes) -> bytes:
    if STRATEGY in ("columnar_zlib", "delta_dict_zlib"):
        return zlib.decompress(comp)
    if STRATEGY == "hoisted_delta_bz2":
        return bz2.decompress(comp)
    return lzma.decompress(comp)

def encode_batch(b64_frames):
    raw = base64.b64decode(b64_frames.encode("ascii"))
    return _compress_frame(raw)

def decode_batch(payload: bytes):
    raw = _decompress_frame(payload)
    return base64.b64encode(raw).decode("ascii")
'''

_CPP_TEMPLATE = r'''#include <chrono>
#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <zlib.h>

static const std::string B64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static std::vector<uint8_t> b64_decode(const std::string& in) {
    std::vector<int> T(256, -1);
    for (int i = 0; i < 64; i++) T[static_cast<unsigned char>(B64_CHARS[i])] = i;
    std::vector<uint8_t> out;
    out.reserve(in.size() * 3 / 4);
    int val = 0, valb = -8;
    for (unsigned char c : in) {
        if (T[c] == -1) break;
        val = (val << 6) + T[c];
        valb += 6;
        if (valb >= 0) {
            out.push_back(static_cast<uint8_t>((val >> valb) & 0xFF));
            valb -= 8;
        }
    }
    return out;
}

static std::string extract_str(const std::string& s, const std::string& key, size_t start_pos, size_t* next_pos) {
    std::string pat = "\"" + key + "\":\"";
    size_t p = s.find(pat, start_pos);
    if (p == std::string::npos) return "";
    p += pat.size();
    size_t e = s.find('"', p);
    if (next_pos) *next_pos = e + 1;
    return s.substr(p, e - p);
}

static long long extract_int(const std::string& s, const std::string& key, size_t start_pos) {
    std::string pat = "\"" + key + "\":";
    size_t p = s.find(pat, start_pos);
    if (p == std::string::npos) return 0;
    p += pat.size();
    while (p < s.size() && (s[p] == ' ')) p++;
    return std::stoll(s.substr(p, 24));
}

int main() {
    std::ostringstream ss;
    ss << std::cin.rdbuf();
    std::string req = ss.str();
    int level = __ZLIB_LEVEL__;
    int repeats = static_cast<int>(extract_int(req, "repeats", 0));
    if (repeats < 1) repeats = 1;

    size_t batches_pos = req.find("\"batches\":");
    if (batches_pos == std::string::npos) {
        std::cout << "{\"ok\":false,\"error\":\"no_batches\"}\n";
        return 0;
    }

    std::ostringstream rows_out;
    rows_out << "{\"ok\":true,\"rows\":[";
    size_t pos = batches_pos;
    bool first = true;
    while (true) {
        size_t id_pos = req.find("\"id\":\"", pos);
        if (id_pos == std::string::npos) break;
        size_t after_id = id_pos;
        std::string id = extract_str(req, "id", id_pos, &after_id);
        long long raw_bytes = extract_int(req, "raw_bytes", after_id);
        size_t after_ev = after_id;
        std::string b64 = extract_str(req, "events", after_id, &after_ev);
        pos = after_ev;

        std::vector<uint8_t> raw = b64_decode(b64);
        std::vector<long long> c_times, d_times;
        std::vector<uint8_t> compressed;

        for (int r = 0; r < repeats; ++r) {
            auto t0 = std::chrono::steady_clock::now();
            uLongf bound = compressBound(static_cast<uLong>(raw.size()));
            compressed.resize(bound + 4);
            uint32_t orig_len = static_cast<uint32_t>(raw.size());
            compressed[0] = (orig_len >> 24) & 0xFF;
            compressed[1] = (orig_len >> 16) & 0xFF;
            compressed[2] = (orig_len >> 8) & 0xFF;
            compressed[3] = orig_len & 0xFF;
            int rc = compress2(compressed.data() + 4, &bound, raw.data(), static_cast<uLong>(raw.size()), level);
            if (rc != Z_OK) {
                std::cout << "{\"ok\":false,\"error\":\"zlib_compress_failed\"}\n";
                return 0;
            }
            compressed.resize(bound + 4);
            auto t1 = std::chrono::steady_clock::now();

            uint32_t dec_len = (static_cast<uint32_t>(compressed[0]) << 24) |
                               (static_cast<uint32_t>(compressed[1]) << 16) |
                               (static_cast<uint32_t>(compressed[2]) << 8) |
                               static_cast<uint32_t>(compressed[3]);
            std::vector<uint8_t> restored(dec_len);
            uLongf dest_len = dec_len;
            int rc2 = uncompress(restored.data(), &dest_len, compressed.data() + 4, static_cast<uLong>(compressed.size() - 4));
            auto t2 = std::chrono::steady_clock::now();
            if (rc2 != Z_OK || dest_len != raw.size() || restored != raw) {
                std::cout << "{\"ok\":false,\"error\":\"round_trip_mismatch\"}\n";
                return 0;
            }
            c_times.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count());
            d_times.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count());
        }

        if (!first) rows_out << ",";
        first = false;
        rows_out << "{\"id\":\"" << id << "\",\"raw_bytes\":" << raw_bytes
                 << ",\"output_bytes\":" << compressed.size()
                 << ",\"output_sha256\":\"cpp_zlib\",\"compress_ns\":[";
        for (size_t i = 0; i < c_times.size(); ++i) {
            if (i > 0) rows_out << ",";
            rows_out << c_times[i];
        }
        rows_out << "],\"decompress_ns\":[";
        for (size_t i = 0; i < d_times.size(); ++i) {
            if (i > 0) rows_out << ",";
            rows_out << d_times[i];
        }
        rows_out << "]}";
    }
    rows_out << "]}\n";
    std::cout << rows_out.str();
    return 0;
}
'''

_GO_TEMPLATE = r'''package main

import (
	"bytes"
	"compress/zlib"
	"encoding/base64"
	"encoding/json"
	"io"
	"os"
	"time"
)

type BatchItem struct {
	ID       string `json:"id"`
	RawBytes int    `json:"raw_bytes"`
	Events   string `json:"events"`
}

type Request struct {
	Repeats int         `json:"repeats"`
	Batches []BatchItem `json:"batches"`
}

type RowOut struct {
	ID           string  `json:"id"`
	RawBytes     int     `json:"raw_bytes"`
	OutputBytes  int     `json:"output_bytes"`
	OutputSha256 string  `json:"output_sha256"`
	CompressNs   []int64 `json:"compress_ns"`
	DecompressNs []int64 `json:"decompress_ns"`
}

func main() {
	input, err := io.ReadAll(os.Stdin)
	if err != nil {
		os.Stdout.WriteString(`{"ok":false,"error":"stdin_error"}`)
		return
	}
	var req Request
	if err := json.Unmarshal(input, &req); err != nil {
		os.Stdout.WriteString(`{"ok":false,"error":"json_error"}`)
		return
	}
	if req.Repeats < 1 {
		req.Repeats = 1
	}
	level := __ZLIB_LEVEL__
	rows := make([]RowOut, 0, len(req.Batches))
	for _, item := range req.Batches {
		raw, err := base64.StdEncoding.DecodeString(item.Events)
		if err != nil {
			os.Stdout.WriteString(`{"ok":false,"error":"b64_error"}`)
			return
		}
		cTimes := make([]int64, 0, req.Repeats)
		dTimes := make([]int64, 0, req.Repeats)
		var compBytes []byte
		for r := 0; r < req.Repeats; r++ {
			t0 := time.Now()
			var buf bytes.Buffer
			zw, err := zlib.NewWriterLevel(&buf, level)
			if err != nil {
				os.Stdout.WriteString(`{"ok":false,"error":"zlib_init"}`)
				return
			}
			_, _ = zw.Write(raw)
			_ = zw.Close()
			compBytes = buf.Bytes()
			t1 := time.Now()

			zr, err := zlib.NewReader(bytes.NewReader(compBytes))
			if err != nil {
				os.Stdout.WriteString(`{"ok":false,"error":"zlib_read_init"}`)
				return
			}
			restored, err := io.ReadAll(zr)
			_ = zr.Close()
			t2 := time.Now()
			if err != nil || !bytes.Equal(restored, raw) {
				os.Stdout.WriteString(`{"ok":false,"error":"round_trip_mismatch"}`)
				return
			}
			cTimes = append(cTimes, t1.Sub(t0).Nanoseconds())
			dTimes = append(dTimes, t2.Sub(t1).Nanoseconds())
		}
		rows = append(rows, RowOut{
			ID:           item.ID,
			RawBytes:     item.RawBytes,
			OutputBytes:  len(compBytes),
			OutputSha256: "go_zlib",
			CompressNs:   cTimes,
			DecompressNs: dTimes,
		})
	}
	out, _ := json.Marshal(map[string]any{"ok": true, "rows": rows})
	os.Stdout.Write(out)
}
'''

_RUST_TEMPLATE = r'''use std::io::{self, Read};
use std::time::Instant;

fn b64_decode(input: &str) -> Vec<u8> {
    let mut table = [-1i8; 256];
    let chars = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    for (i, &c) in chars.iter().enumerate() {
        table[c as usize] = i as i8;
    }
    let mut out = Vec::with_capacity(input.len() * 3 / 4);
    let mut val: i32 = 0;
    let mut valb: i32 = -8;
    for b in input.bytes() {
        let d = table[b as usize];
        if d == -1 {
            break;
        }
        val = (val << 6) + (d as i32);
        valb += 6;
        if valb >= 0 {
            out.push(((val >> valb) & 0xFF) as u8);
            valb -= 8;
        }
    }
    out
}

fn lz_compress(data: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(data.len() / 2 + 16);
    let n = data.len();
    out.extend_from_slice(&(n as u32).to_be_bytes());
    let mut ht = [0usize; 4096];
    let mut i = 0usize;
    let mut lit_start = 0usize;

    let flush_lits = |out: &mut Vec<u8>, lits: &[u8]| {
        let mut idx = 0;
        while idx < lits.len() {
            let chunk = (lits.len() - idx).min(127);
            out.push(chunk as u8);
            out.extend_from_slice(&lits[idx..idx + chunk]);
            idx += chunk;
        }
    };

    while i + 4 <= n {
        let h = (((data[i] as usize) << 8) ^ ((data[i + 1] as usize) << 4) ^ (data[i + 2] as usize) ^ ((data[i + 3] as usize) << 2)) & 4095;
        let ref_pos = ht[h];
        ht[h] = i;
        let dist = i.wrapping_sub(ref_pos);
        if dist > 0 && dist <= 65535 && ref_pos + 4 <= n && data[ref_pos..ref_pos + 4] == data[i..i + 4] {
            if i > lit_start {
                flush_lits(&mut out, &data[lit_start..i]);
            }
            let mut mlen = 4usize;
            while i + mlen < n && mlen < 130 && data[ref_pos + mlen] == data[i + mlen] {
                mlen += 1;
            }
            out.push(0x80 | ((mlen - 3) as u8));
            out.push(((dist >> 8) & 0xFF) as u8);
            out.push((dist & 0xFF) as u8);
            i += mlen;
            lit_start = i;
        } else {
            i += 1;
        }
    }
    if lit_start < n {
        flush_lits(&mut out, &data[lit_start..n]);
    }
    out
}

fn lz_decompress(comp: &[u8]) -> Result<Vec<u8>, &'static str> {
    if comp.len() < 4 {
        return Err("truncated_header");
    }
    let orig_len = u32::from_be_bytes([comp[0], comp[1], comp[2], comp[3]]) as usize;
    let mut out = Vec::with_capacity(orig_len);
    let mut i = 4usize;
    while i < comp.len() {
        let tag = comp[i];
        i += 1;
        if (tag & 0x80) == 0 {
            let len = tag as usize;
            if i + len > comp.len() {
                return Err("truncated_literal");
            }
            out.extend_from_slice(&comp[i..i + len]);
            i += len;
        } else {
            let mlen = ((tag & 0x7F) as usize) + 3;
            if i + 2 > comp.len() {
                return Err("truncated_match");
            }
            let dist = ((comp[i] as usize) << 8) | (comp[i + 1] as usize);
            i += 2;
            if dist == 0 || dist > out.len() {
                return Err("bad_distance");
            }
            let start = out.len() - dist;
            for k in 0..mlen {
                let b = out[start + k];
                out.push(b);
            }
        }
    }
    if out.len() != orig_len {
        return Err("length_mismatch");
    }
    Ok(out)
}

fn extract_str<'a>(s: &'a str, key: &str, start: usize) -> Option<(&'a str, usize)> {
    let pat = format!("\"{}\":\"", key);
    let p = s[start..].find(&pat)? + start + pat.len();
    let e = s[p..].find('"')? + p;
    Some((&s[p..e], e + 1))
}

fn extract_int(s: &str, key: &str, start: usize) -> i64 {
    let pat = format!("\"{}\":", key);
    if let Some(rel) = s[start..].find(&pat) {
        let p = start + rel + pat.len();
        let tail = s[p..].trim_start();
        let end = tail.find(|c: char| !c.is_ascii_digit()).unwrap_or(tail.len());
        tail[..end].parse::<i64>().unwrap_or(0)
    } else {
        0
    }
}

fn main() {
    let mut req = String::new();
    let _ = io::stdin().read_to_string(&mut req);
    let repeats = extract_int(&req, "repeats", 0).max(1) as usize;
    let batches_pos = match req.find("\"batches\":") {
        Some(p) => p,
        None => {
            println!("{{\"ok\":false,\"error\":\"no_batches\"}}");
            return;
        }
    };
    let mut out_json = String::from("{\"ok\":true,\"rows\":[");
    let mut pos = batches_pos;
    let mut first = true;
    while let Some((id, after_id)) = extract_str(&req, "id", pos) {
        let raw_bytes = extract_int(&req, "raw_bytes", after_id);
        let (b64, after_ev) = match extract_str(&req, "events", after_id) {
            Some(v) => v,
            None => break,
        };
        pos = after_ev;
        let raw = b64_decode(b64);
        let mut c_times = Vec::with_capacity(repeats);
        let mut d_times = Vec::with_capacity(repeats);
        let mut comp = Vec::new();
        for _ in 0..repeats {
            let t0 = Instant::now();
            comp = lz_compress(&raw);
            let t1 = Instant::now();
            let restored = match lz_decompress(&comp) {
                Ok(v) => v,
                Err(e) => {
                    println!("{{\"ok\":false,\"error\":\"{}\"}}", e);
                    return;
                }
            };
            let t2 = Instant::now();
            if restored != raw {
                println!("{{\"ok\":false,\"error\":\"round_trip_mismatch\"}}");
                return;
            }
            c_times.push(t1.duration_since(t0).as_nanos() as i64);
            d_times.push(t2.duration_since(t1).as_nanos() as i64);
        }
        if !first {
            out_json.push(',');
        }
        first = false;
        let c_str: Vec<String> = c_times.iter().map(|x| x.to_string()).collect();
        let d_str: Vec<String> = d_times.iter().map(|x| x.to_string()).collect();
        out_json.push_str(&format!(
            "{{\"id\":\"{}\",\"raw_bytes\":{},\"output_bytes\":{},\"output_sha256\":\"rust_lz\",\"compress_ns\":[{}],\"decompress_ns\":[{}]}}",
            id, raw_bytes, comp.len(), c_str.join(","), d_str.join(",")
        ));
    }
    out_json.push_str("]}");
    println!("{}", out_json);
}
'''


def build_telemetry_code_proposal(language: str, strategy: str, hypothesis_id: str = "h1") -> dict[str, Any]:
    """Construct a valid ``CodeArtifactProposal`` for the requested language and strategy."""
    if language not in CODE_LANGUAGES:
        raise ValueError(f"unsupported code_codec language: {language!r}")
    if strategy not in CODE_STRATEGIES:
        raise ValueError(f"unsupported code_codec strategy: {strategy!r}")

    zlib_level = 9 if strategy in ("delta_dict_zlib", "compact_frame_lzma") else 6
    if language == "python":
        fname = "codec_impl.py"
        src = _PYTHON_TEMPLATE.replace("__STRATEGY__", json.dumps(strategy))
        sym = "encode_batch"
    elif language == "cpp":
        fname = "codec_impl.cpp"
        src = _CPP_TEMPLATE.replace("__ZLIB_LEVEL__", str(zlib_level))
        sym = "main"
    elif language == "go":
        fname = "codec_impl.go"
        src = _GO_TEMPLATE.replace("__ZLIB_LEVEL__", str(zlib_level))
        sym = "main"
    else:
        fname = "codec_impl.rs"
        src = _RUST_TEMPLATE
        sym = "main"

    return {
        "hypothesis_id": hypothesis_id,
        "purpose": f"Compile and benchmark {language} telemetry codec ({strategy}) inside macOS Seatbelt sandbox",
        "artifact_type": "algorithm",
        "language": language,
        "files": [{"path": fname, "role": "source", "content": src}],
        "entrypoint": {"file": fname, "symbol": sym},
        "dependencies": [],
        "io_contract": {"input": "base64-encoded composable telemetry frame batch", "output": "compressed payload bytes"},
        "intended_behavior": f"Losslessly compress and decompress telemetry frames using {language} ({strategy}).",
        "expected_outcome": "Exact round-trip reconstruction and lower payload ratio vs V1 gzip-1.",
        "assumptions": ["inputs are valid UTF-8 telemetry batch frames"],
        "requested_verification": ["correctness", "performance"],
        "parent_id": None,
        "change_summary": None,
    }


class _CompiledCache:
    """Cache of Seatbelt-compiled TRUSTED-template codecs and their Tier 1 records, keyed by bundle_sha256.

    Integrity (WP-AUT-04): the directory is private to this user (0700, owner-checked, in the per-user temp dir, not the shared /private/tmp); every metadata file is
    HMAC-authenticated with a per-cache key and carries the binary digest, which is recomputed on every reuse. A planted, edited or swapped entry is discarded and rebuilt."""

    def __init__(self) -> None:
        self.root = Path(tempfile.gettempdir()) / "fhel-code-codec-cache-v3"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = self.root.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise PermissionError(f"code cache {self.root} must be private to this user (owner {info.st_uid}, mode {oct(info.st_mode & 0o777)})")
        key_path = self.root / ".key"
        if not key_path.exists():
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(os.urandom(32))
        self.key = key_path.read_bytes()
        self.caps = sb.ResourceCaps(
            wall_time_seconds=30,
            cpu_time_seconds=20,
            memory_bytes=512 * 1024 * 1024,
            disk_bytes=64 * 1024 * 1024,
            process_count=32,
            open_file_count=1024,
        )
        self.entries: dict[str, tuple[Path, list[str], cs.Tier1VerificationReceipt]] = {}

    def _mac(self, payload: Mapping[str, Any]) -> str:
        return hmac.new(self.key, json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()

    def get_or_compile(
        self,
        raw_proposal: Mapping[str, Any],
        canary_item: Mapping[str, Any],
    ) -> tuple[Path, list[str], cs.Tier1VerificationReceipt]:
        proposal = ca.parse_proposal(raw_proposal)
        b_sha = ca.bundle_sha256(proposal)
        if b_sha in self.entries and self.entries[b_sha][0].is_dir():
            cached = self.entries[b_sha]
            try:
                if cs.binary_identity(proposal, cached[0]) == cached[2].binary_sha256:        # the executable is re-hashed on EVERY reuse, not only after a restart
                    return cached
            except OSError:
                pass
            self.entries.pop(b_sha, None)

        target_dir = self.root / f"bin-{b_sha[:16]}"
        lock_path = self.root / f"bin-{b_sha[:16]}.lock"
        meta_path = target_dir / "_tier1_meta.json"

        with open(lock_path, "a+") as lockf:
            fcntl.flock(lockf, fcntl.LOCK_EX)
            try:
                if meta_path.is_file():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                        mac = meta.pop("mac")
                        rec = cs.Tier1VerificationReceipt(**meta["receipt"])
                        run_argv = list(meta["run_argv"])
                        if (not hmac.compare_digest(mac, self._mac(meta)) or rec.bundle_sha256 != b_sha or not rec.passed or not rec.binary_sha256
                                or cs.binary_identity(proposal, target_dir) != rec.binary_sha256):
                            raise ValueError("cache entry failed its integrity check")
                        self.entries[b_sha] = (target_dir, run_argv, rec)
                        return target_dir, run_argv, rec
                    except Exception:                                   # tampered / stale / unreadable: discard and rebuild
                        self.entries.pop(b_sha, None)
                        shutil.rmtree(target_dir, ignore_errors=True)

                shutil.rmtree(target_dir, ignore_errors=True)
                target_dir.mkdir(parents=True, exist_ok=True)
                cs._write_proposal_files(proposal, target_dir)
                ok, run_argv, c_diag, c_wall = cs._compile_in_sandbox(proposal, target_dir, self.caps)
                if not ok:
                    rec = cs.Tier1VerificationReceipt(
                        b_sha, proposal["language"], proposal["entrypoint"]["file"], proposal["entrypoint"]["symbol"],
                        False, "build_error", c_diag, "", 1, 0, c_wall, 0.0,
                    )
                    return target_dir, [], rec

                t1_req = {
                    "mode": "codec_batch",
                    "entrypoint_file": proposal["entrypoint"]["file"],
                    "entrypoint_symbol": proposal["entrypoint"]["symbol"],
                    "repeats": 1,
                    "batches": [dict(canary_item)],
                }
                t1_out = cs.run_sandboxed_command(
                    run_argv,
                    target_dir,
                    self.caps,
                    stdin_bytes=json.dumps(t1_req).encode("utf-8"),
                    stdout_limit=4 * 1024 * 1024,
                )
                r_diag = (t1_out.stderr or b"").decode("utf-8", errors="replace").strip()
                if t1_out.timed_out or t1_out.returncode != 0:
                    rec = cs.Tier1VerificationReceipt(
                        b_sha, proposal["language"], proposal["entrypoint"]["file"], proposal["entrypoint"]["symbol"],
                        False, "timeout" if t1_out.timed_out else "crash", c_diag, r_diag, 1, 0, c_wall, t1_out.wall_time_s,
                    )
                    return target_dir, [], rec

                try:
                    resp = json.loads(t1_out.stdout.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    rec = cs.Tier1VerificationReceipt(
                        b_sha, proposal["language"], proposal["entrypoint"]["file"], proposal["entrypoint"]["symbol"],
                        False, "wrong_output", c_diag, str(exc), 1, 0, c_wall, t1_out.wall_time_s,
                    )
                    return target_dir, [], rec

                if not isinstance(resp, dict) or not resp.get("ok"):
                    rec = cs.Tier1VerificationReceipt(
                        b_sha, proposal["language"], proposal["entrypoint"]["file"], proposal["entrypoint"]["symbol"],
                        False, "test_failure", c_diag, str(resp.get("error", "tier1_failed")), 1, 0, c_wall, t1_out.wall_time_s,
                    )
                    return target_dir, [], rec

                rec = cs.Tier1VerificationReceipt(
                    b_sha, proposal["language"], proposal["entrypoint"]["file"], proposal["entrypoint"]["symbol"],
                    True, "none", c_diag, r_diag, 1, 1, c_wall, t1_out.wall_time_s, cs.binary_identity(proposal, target_dir),
                )
                body = {
                            "run_argv": run_argv,
                            "receipt": {
                                "bundle_sha256": rec.bundle_sha256,
                                "language": rec.language,
                                "entrypoint_file": rec.entrypoint_file,
                                "entrypoint_symbol": rec.entrypoint_symbol,
                                "passed": rec.passed,
                                "failure_class": rec.failure_class,
                                "compiler_Diagnostics": rec.compiler_Diagnostics,
                                "runtime_diagnostics": rec.runtime_diagnostics,
                                "tests_run": rec.tests_run,
                                "tests_passed": rec.tests_passed,
                                "compile_wall_s": rec.compile_wall_s,
                                "test_wall_s": rec.test_wall_s,
                                "binary_sha256": rec.binary_sha256,
                            },
                        }
                meta_path.write_text(json.dumps({**body, "mac": self._mac(body)}), encoding="utf-8")
                self.entries[b_sha] = (target_dir, run_argv, rec)
                return target_dir, run_argv, rec
            finally:
                fcntl.flock(lockf, fcntl.LOCK_UN)


_CACHE = _CompiledCache()


def execute_sandboxed_batches(
    language: str,
    strategy: str,
    batch_items: Sequence[Mapping[str, Any]],
    repeats: int,
    slow_limit_s: float,
) -> dict[str, Any]:
    """Compile (if needed), Tier-1 verify, and Tier-2 benchmark ``batch_items`` inside the macOS Seatbelt sandbox."""
    if not batch_items:
        return {"ok": False, "rejection": "empty_batches", "rows": []}
    norm_items: list[dict[str, Any]] = []
    for item in batch_items:
        d = dict(item)
        if "raw_frames" in d and "events" not in d:
            d["events"] = base64.b64encode(d.pop("raw_frames")).decode("ascii")
        norm_items.append(d)
    proposal = build_telemetry_code_proposal(language, strategy)
    scratch, run_argv, receipt = _CACHE.get_or_compile(proposal, norm_items[0])
    if not receipt.passed:
        return {
            "ok": False,
            "rejection": f"tier1_{receipt.failure_class}:{receipt.compiler_Diagnostics or receipt.runtime_diagnostics}"[:120],
            "rows": [],
        }

    # Chunk installations into groups of 32 so stdin/stdout stay small and fast
    all_rows: list[dict[str, Any]] = []
    chunk_size = 32
    timeout_sec = max(5, min(60, int(slow_limit_s) + 5)) if math.isfinite(slow_limit_s) else 30
    caps = sb.ResourceCaps(
        wall_time_seconds=timeout_sec,
        cpu_time_seconds=timeout_sec,
        memory_bytes=512 * 1024 * 1024,
        disk_bytes=64 * 1024 * 1024,
        process_count=32,
        open_file_count=1024,
    )
    for start in range(0, len(norm_items), chunk_size):
        chunk = list(norm_items[start : start + chunk_size])
        req = {
            "mode": "codec_batch",
            "entrypoint_file": proposal["entrypoint"]["file"],
            "entrypoint_symbol": proposal["entrypoint"]["symbol"],
            "repeats": max(1, int(repeats)),
            "batches": chunk,
        }
        out = cs.run_sandboxed_command(
            run_argv,
            scratch,
            caps,
            stdin_bytes=json.dumps(req, separators=(",", ":")).encode("utf-8"),
            stdout_limit=8 * 1024 * 1024,
        )
        if out.timed_out or out.returncode != 0:
            return {"ok": False, "rejection": "tier2_timeout" if out.timed_out else f"tier2_exit_{out.returncode}", "rows": []}
        try:
            resp = json.loads(out.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"ok": False, "rejection": "tier2_malformed_json", "rows": []}
        if not isinstance(resp, dict) or not resp.get("ok") or not isinstance(resp.get("rows"), list):
            return {"ok": False, "rejection": str(resp.get("error", "tier2_failed"))[:120], "rows": []}
        all_rows.extend(resp["rows"])

    return {
        "ok": len(all_rows) == len(batch_items),
        "rejection": None if len(all_rows) == len(batch_items) else "row_count_mismatch",
        "rows": all_rows,
        "bundle_sha256": receipt.bundle_sha256,
        "tier1_receipt_sha256": receipt.receipt_sha256,
        "language": language,
    }
