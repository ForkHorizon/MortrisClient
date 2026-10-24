# Heuriva → MORTRIS analytics research handoff

Phase 1 deliverable (2026-10-24). Read-only import of Heuriva's M7/V8 research into this repo. **No SDK, server or benchmark was touched.** Start with `RESEARCH_SUMMARY.md`, then `INTEGRATION_CANDIDATES.md`.

## Layout
| Path | Content |
|---|---|
| `RESEARCH_SUMMARY.md` | Engineering digest, every claim cites a file below |
| `INTEGRATION_CANDIDATES.md` | Opportunities for the SDK, with evidence grade. NOT a plan |
| `MANIFEST.json` | Per file: origin repo/path/commit/git blob, SHA-256, bytes, kind, transform, safe_to_commit |
| `build_manifest.py` | Regenerates the manifest (does not modify imported files) |
| `reports/` | 26 Heuriva documents/configs, flattened names (`/` → `__`), verbatim |
| `implementations/` | `research/telemetry-v7/` (C# replay harness + Go decoder driver) and `src/fhel/problems/telemetry*.py` (Python bridge/evaluator), verbatim |
| `benchmarks/` | Two aggregate sweep results (`trusted_m7_*_20261021.json`), no event data |
| `manifests/` | Heuriva's own data manifest (hashes of local corpora) and schema audit |

## Provenance (explicit commits, `main` was not used)
- Heuriva PR #25 head `2d8f761813545e9abdbc2a536c4d2e36f1d3226a` (`daliys/fix-over-limit-stop`, OPEN, unmerged): everything except the two files below.
- Heuriva PR #24 head `2cc7bd9e1a2177847014045fe3519b480984d1a9` (`daliys/live-field-test-20261023`, OPEN, unmerged): `FOUR_HOUR_LIVE_*` reports only. PR #25 does **not** contain them.
- Heuriva `main` at import: `f7f96e986e77c4698f5eea0c4079b3a00b2cd36c`.
- Source checkout: `~/Daliys/AI_Test_PlayGround/Heuriva` (fetched, not modified). `.local/mortris-v8/` files are untracked there; their hashes are in `MANIFEST.json`, no git commit exists for them.

## NOT imported (by design)
- Raw telemetry: `MortrisV7Data/experiments/night-run~/work/puzzle-1m.jsonl.gz` (sha256 `8475bd3d…56ca3`, 129,766,326 B), `snapshots/.../puzzle-1m-2026-10-20.jsonl.gz` (`712ecd9f…`), `puzzle-2026-10-16.jsonl.gz` (`abf84a30…`), `replay_real_20k.jsonl`. They already live in the ignored `MortrisV7Data/` (3.6 GB, untracked, don't commit). Hashes in `manifests/heuriva_data_manifest_20261021.json`.
- Heuriva campaign databases (`.local/mortris-v8/night*-campaign-*/knowledge.sqlite3`, ~14 MB total, local only): contain the 616 paired rows behind the tables. Not copied; rerun-free access only on request.
- Catalog/dictionaries the Heuriva evaluator needs (`catalog-real-raw.json`, `dict-real-raw-{16,32}.bin`, in `MortrisV7Data/snapshots/MORTRIS_handoff-v7~/docs/Theory~/transport-v7/06-experiments/results/`): dictionaries are trained on real player data, so referenced, not committed.
- Credential-like key/cert files in `MortrisV7Data` (Firebase MITM CA etc.): never touched.
- Heuriva model conversation logs, ledgers, `lab.sqlite3`, FHCE archive.

## Missing local dependencies to re-run anything
.NET 10 SDK (replay csproj), Go (decoder in `MortrisV7Data/.../server/internal/transportv7`), native `daliys_zstd` library, Python 3.13 + `uv`, the Heuriva checkout (`fhel` package, evaluator pinned at telemetry evaluator v6). The replay harness (`implementations/research__telemetry-v7__*`) compiles against `M7*.cs` sources from the Mortris client snapshot, not included here.

## Refresh procedure
1. `git -C ~/Daliys/AI_Test_PlayGround/Heuriva fetch origin` and pick **explicit** commits (PR heads or merged main).
2. Never overwrite: create `reports-<date>/` next to the old folder, or add new files; keep older imports for diffing.
3. Update the commit constants in `build_manifest.py`, run it, diff `MANIFEST.json`. A changed SHA for an existing path means Heuriva rewrote a result: record it in `notes/CHANGELOG.md`, don't silently replace.
4. Secret scan (`grep -rIE 'BEGIN (RSA|PRIVATE)|ghp_|gho_'`), then commit.

## Caveat that applies to every number here
Everything is **development-cohort evidence on one macOS host**, payload bytes of *reconstructed* V1/M7 bodies (not captured traffic). The holdout is exposed, no confirmation cohort exists. Nothing here is a measured improvement of the MORTRIS product.
