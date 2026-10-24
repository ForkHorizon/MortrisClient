#!/usr/bin/env python3
"""Adds the SDK's session lifecycle events to a V7 catalog (server-side catalog JSON: events, keys, shapes, masks).
Usage: add_lifecycle_shapes.py IN.json OUT.json
Without these shapes a packet containing a lifecycle event is not encodable and that batch is sent through V1 instead (correct, but 5-10x bigger).
Types: 0 int, 1 string, 2 bool. Event ids are appended after the existing ones; keys are appended after the existing ones."""
import json, sys
INT, STRING, BOOL = 0, 1, 2
SHAPES = {
    "sys_session_start": {"cold_start": BOOL},
    "sys_app_background": {"active_ms": INT, "reason": STRING},
    "sys_app_foreground": {"new_session": BOOL, "paused_ms": INT},
    "sys_session_end": {"active_ms": INT, "background": BOOL, "duration_ms": INT, "reason": STRING},
}
catalog = json.load(open(sys.argv[1]))
shapes = catalog["shapes"]
for name, fields in SHAPES.items():
    sorted_fields = [[k, t] for k, t in sorted(fields.items())]
    if not any(s[0] == name and s[1] == sorted_fields for s in shapes):
        shapes.append([name, sorted_fields])        # new shapes go last: existing shape ids (what packets carry) do not move
# The server requires event ids to be the alphabetical rank (1..N) and keys sorted; masks are bit sets over key positions.
names = sorted({s[0] for s in shapes} | set(catalog["events"]))
catalog["events"] = {name: i + 1 for i, name in enumerate(names)}
catalog["keys"] = sorted(set(catalog["keys"]) | {k for s in shapes for k, _ in s[1]})
position = {k: i for i, k in enumerate(catalog["keys"])}
catalog["masks"] = [sum(1 << position[k] for k, _ in s[1]) for s in shapes]
if len(catalog["events"]) > 255:
    sys.exit("too many events for one catalog")
json.dump(catalog, open(sys.argv[2], "w"), separators=(",", ":"))
print("shapes", len(shapes), "events", len(catalog["events"]), "keys", len(catalog["keys"]))
