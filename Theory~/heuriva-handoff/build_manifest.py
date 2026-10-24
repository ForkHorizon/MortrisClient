#!/usr/bin/env python3
"""Offline: refreshes sha256/bytes in MANIFEST.json for every file under the handoff and registers new files.
Needs NO Heuriva checkout; provenance of the original import is kept from the existing manifest.
Run with --check to only verify (exit 1 on mismatch). Imported files are never modified."""
import hashlib, json, os, sys, datetime
m = json.load(open("MANIFEST.json")); known = {f["path"]: f for f in m["files"]}
DERIVED = {"data/summarize.py": "written in this repo", "data/candidate_summary.csv": "derived by data/summarize.py from data/all_measurements.csv",
           "data/all_measurements.csv": "export of the `measurements` tables of the six data/*.knowledge.sqlite3 (cumulative stores: duplicates across campaigns, see summarize.py)"}
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
bad = 0
for top in ("reports", "implementations", "benchmarks", "manifests", "data"):
    for n in sorted(os.listdir(top)):
        rel = f"{top}/{n}"; h = sha(rel)
        if rel in known:
            if known[rel]["sha256"] != h:
                bad += 1; print("CHANGED", rel)
                if "--check" not in sys.argv: known[rel].update(sha256=h, bytes=os.path.getsize(rel))
            continue
        e = {"path": rel, "bytes": os.path.getsize(rel), "sha256": h, "imported": datetime.date.today().isoformat(), "safe_to_commit": True}
        if n.endswith(".knowledge.sqlite3"):
            e.update(kind="measurement-raw-aggregate", origin_repo="ForkHorizon/Heuriva (untracked local)", origin_path=".local/mortris-v8/%s/knowledge.sqlite3" % n[:-len(".knowledge.sqlite3")],
                     origin_commit="n/a (ignored local file, copied 2026-10-24 via sqlite backup from a read-only immutable open)", transform="verbatim content (sqlite backup API), contains bytes/ns per measurement, no events")
        else:
            e.update(kind="derived-analysis", origin_repo="this repo", origin_path=DERIVED.get(rel, ""), transform="generated")
        known[rel] = e; print("ADDED", rel)
for p in list(known):
    if not os.path.exists(p): print("MISSING", p); bad += 1
if "--check" not in sys.argv:
    m["files"] = [known[k] for k in sorted(known)]; json.dump(m, open("MANIFEST.json", "w"), indent=1)
sys.exit(1 if bad and "--check" in sys.argv else 0)
