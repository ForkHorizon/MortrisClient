#!/usr/bin/env python3
"""Regenerates MANIFEST.json for this handoff. Run from this directory; never edits imported files.
Provenance is taken from the git commits named below (read-only access to the Heuriva checkout)."""
import hashlib, json, os, subprocess, datetime
HV = os.path.expanduser("~/Daliys/AI_Test_PlayGround/Heuriva")
PR25 = "2d8f761813545e9abdbc2a536c4d2e36f1d3226a"  # ForkHorizon/Heuriva PR #25 head daliys/fix-over-limit-stop
PR24 = "2cc7bd9e1a2177847014045fe3519b480984d1a9"  # ForkHorizon/Heuriva PR #24 head daliys/live-field-test-20261023
LIVE = {"docs__architecture-v2__FOUR_HOUR_LIVE_FIELD_REVIEW_2026-10-23.md", "research__mortris-v8__FOUR_HOUR_LIVE_RESEARCH_REPORT_2026-10-23.md"}
LOCAL = {"benchmarks/trusted_m7_full_dev_20261021.json", "benchmarks/trusted_m7_dev_sweep_20261021.json",
         "manifests/heuriva_schema_audit.json", "manifests/heuriva_data_manifest_20261021.json"}
def sha(p):
    h = hashlib.sha256(); h.update(open(p, "rb").read()); return h.hexdigest()
def kind(rel):
    if rel.startswith("benchmarks/"): return "measurement-aggregate"
    if rel.startswith("manifests/"): return "provenance-metadata"
    if rel.startswith("implementations/"): return "source"
    if "campaign_template" in rel: return "benchmark-config"
    return "documentation"
files = []
for top in ("reports", "implementations", "benchmarks", "manifests"):
    for n in sorted(os.listdir(top)):
        rel = f"{top}/{n}"
        e = {"path": rel, "bytes": os.path.getsize(rel), "sha256": sha(rel), "kind": kind(rel),
             "imported": "2026-10-24", "safe_to_commit": True}
        if rel in LOCAL:
            e.update(origin_repo="ForkHorizon/Heuriva (untracked local .local/mortris-v8, not in git)",
                     origin_path=".local/mortris-v8/" + n.replace("heuriva_schema_audit", "schema_audit").replace("heuriva_data_manifest_20261021", "data_manifest"),
                     origin_commit="n/a (ignored local file, mtime 2026-10-21)", transform="verbatim" if top == "benchmarks" or "schema" in rel else "re-serialized JSON (indent=1), content unchanged")
        else:
            c = PR24 if n in LIVE else PR25
            op = n.replace("__", "/")
            blob = subprocess.check_output(["git", "-C", HV, "rev-parse", f"{c}:{op}"], text=True).strip()
            e.update(origin_repo="ForkHorizon/Heuriva", origin_path=op, origin_commit=c,
                     origin_pr=24 if c == PR24 else 25, git_blob=blob, transform="verbatim (git show, flattened path)")
        files.append(e)
json.dump({"generated": datetime.date.today().isoformat(), "heuriva_prs": {"25": PR25, "24": PR24, "main": "f7f96e986e77c4698f5eea0c4079b3a00b2cd36c"}, "files": files}, open("MANIFEST.json", "w"), indent=1)
print(len(files), "files")
