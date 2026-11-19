# V7 reproducible research

All experiments are local. `run_all.sh` never connects to production. The optional,
explicit `export_day.sh` does only a `BEGIN READ ONLY` PostgreSQL COPY through SSH.
Do not re-export when reproducing the frozen results: the saved dump SHA identifies
exactly the day tested. Production retention/backfill can change a later export.

From this folder: `./run_all.sh` (several minutes). Defaults to the existing V3
virtualenv. Or use `PY=/absolute/path/to/python ./run_all.sh`, with frozen V6's
requirements installed. Dependencies: Python3.14/zstandard0.25, .NET10 SDK,
Go1.27.2, zstd1.5.7 (headers/library currently under `/opt/homebrew/opt/zstd`).
No new project dependency is introduced. Linux needs the cgo/loader search paths
adjusted; these host scripts document the measured macOS setup.

`results/private/puzzle-2026-10-16.jsonl.gz` is the immutable local day copy,
SHA256 `abf84a30a9fda133d89c98fca91d256156f4c3fd6960a35312d86de5b13e68ec`.
Private telemetry/derived actual-value fixtures and real trained dictionaries are
ignored by Git. Do not send this dump or dictionary bytes to public artifacts.
`results/real-audit.json` contains only aggregate evidence and hashes.

`transport7.py`: project-bound catalog, generic value columns, bounded framing,
dictionary identity and decode authorization. Reuses neutral frozen V6 helpers,
not V6's game-specific prediction/reference paths. Unsupported schema -> explicit
V1 fallback in the harness. `game_cleanup.py` is separate, Puzzle-only, opt-in
migration simulation. It preserves mismatched/truncated/non-derivable hashes.

`bench7.py` tests synthetic base/rich/alt/drift, train202 and independent seeds
101/1729/2601, dictionaries16/32KiB. `bench_real7.py` uses disjoint installations
from the private day; exact stored *typed event* reconstruction is checked at
all V7 modes. V1 bodies are reconstructed, not original captured HTTP requests.

`native/Columns.cs` packs typed values with caller-owned buffers and native zstd
reuse. `Columns.csproj` runs the host benchmark, `UnityColumns.csproj` only verifies
netstandard2.1 compilation. `go/main.go` independently decompresses and validates
all metadata/value columns against C# fixture expectations; it is not an HTTP
receiver or a complete M7 framing service. C#/Python/Go agree on valid UTF-8,
UUID/hex, int64 overflow edges, uint64, bool/null, IEEE signed zero and Decimal
lexemes. V7 normalizes JSON property order before schema lookup and preserves all typed
values rather than insignificant object key order. Native C# uses raw IEEE float mode; Python may choose exact fixed-point,
so interoperability checks semantic roundtrip rather than byte equality.

Saved `verification.json` separates test passes from unmet traffic goals and
unmeasured Unity/phone/battery targets. A verification PASS does not mean V7 met
those targets. `snapshot.py` checks594 frozen previous-research/SDK/game files.


`./run_numeric.sh` reproduces the optional generic signed-integer model (flag2).
It trains separate16/32KiB dictionaries, uses the same disjoint real installs,
and validates six additional C#/Python/Go fixtures, including all five opcodes.
The frozen default benchmark remains in bench-real.json; candidate results are
in numeric-benchmark.json. Host zero-GC/CPU evidence remains stage-limited.


`./run_unity7.sh` builds an isolated Android ARM64 Development IL2CPP APK and
runs the manifest fixtures (now16, including4 string-model cases) on each existing Mortris_API_35/4KB and Pixel_8/16KB AVD. Unity Editor Mono is
checked independently. It uses calibrated Unity ProfilerRecorder GC.Alloc,
not GC.GetAllocatedBytesForCurrentThread (which returned0 even for a control
allocation). Reports are unity-editor.json and unity-android.json, raw outputs
remain private. Native zstd is compiled from pinned1.5.7 source using the already
installed NDK. No Editor installation, Puzzle app or production endpoint changes.
The complete SDK ingress/framing/delivery and physical-phone thermal/FPS/CPU
criteria remain outside these scoped results.

`./run_tables.sh` adds the generic Python string model (flag4), metadata tables
(flag16), and a catalog with logical string types independent of UUID/hex content.
It expects the prior baseline/numeric artifacts and the private immutable day.
All16 unit tests and per-batch exact roundtrips run;16/32KiB dictionaries use only
train installations. `profile_remaining7.py` is a counterfactual diagnostic that
replaces information with constants; its marginal gains are not lossless results
and must not be added. Model selection on this holdout is exploratory;
confirmation needs separate data. Reports:07-string-table-evaluation.md and
results/tables-benchmark.json. Existing default/numeric frame outputs are unchanged.

`./run_native_tables.sh` ports string flag4 to preallocated C# workspaces and an
independent Go decoder; metadata flag16 is intentionally still Python-only.
It creates4 extra fixtures: forced opcodes0..4, Unicode500 and actual raw/clean100.
All4 have0 host GC and byte-exact Python parity, plus independent Go validation.
`go test` rejects malformed string refs/counts/tags/UTF-8. Then run `./run_unity7.sh`
to consume all16 fixtures, rebuild the research APK and verify/freeze the complete
evidence snapshot. Current Unity Mono/Android IL2CPP4KB/16KB results cover all16
with calibrated0 GC.Alloc. These remain pretyped-stage measurements, not full SDK
or physical-phone/FPS/thermal proof. Raw/clean size totals remain the Python
holdout benchmark; native parity does not turn them into a full native corpus run.

`./run_cross.sh` tests a separate generic cross-column integer predictor against
the same train/holdout: up to16 earlier signed columns, same-row reference or0,
exact add/subtract residuals with overflow checks. It does not modify M7 flags,
the SDK or native/Unity codecs. The result uses compressed raw columns plus a
header/CRC byte allowance; it is not an actual negotiated M7 frame measurement.
19 tests include prior cases and new malformed/missing/overflow/window checks;
every real batch restores the old raw stream byte-for-byte. See08 report and
results/cross-benchmark.json; old Unity CPU/GC evidence does not cover this probe.

`./run_frames.sh` builds native/Frames.csproj and the netstandard2.1 FrameEncoder.
It forms actual C# M7 packets (header/catalog/epoch/dict IDs + sizes + body + CRC).
All8 flag combinations, raw/no-dict, too-small destination recovery and a compressed
500-event raw body above the frame cap are tested,1000 iterations with calibrated
host0 GC. CRC-valid malformed headers/bodies and wrong auth are rejected by the
independent Python decoder. All653 supported real batches per raw/clean variant
are then encoded by C# and decoded against original typed values,200 fallback
events paid: byte totals exactly match prior Python results.19 Python tests also
run. Inputs/manifests/catalog assets/actual packets remain private/frames.
This is host full-packet proof with pretyped input, not Unity framing or SDK
ingress/queue/network/delivery/Go M7 server proof. See09-full-packet-validation.md.

`./run_go_frames.sh` consumes the private case index/assets exported by run_frames.sh.
Go API NewFrameDecoder/Decode derives events and field ownership from the actual
project catalog/alias snapshots and external authenticated project/origin, with
bounded CRC/size/zstd/type validation. It receives no fixture row/column/source
value hints. Python compares the decoded JSON separately; IEEE bits use original
typed input because frozen V1 f32 formatting normalizes -0. All1316 packets pass,
112 malformed/auth cases reject. Raw-body fuzz wraps arbitrary bytes in a valid
header/CRC; it is not zstd/HTTP fuzz. Output:go-frames.json and go-frame-*.log;
private decoded event data stays under private/frames. HTTP/persistence/ACK and
SDK integration remain unimplemented;10 report states the complete scope.
