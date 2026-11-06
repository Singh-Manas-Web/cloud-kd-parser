"""Seconds from Pod creation to Ready, from `kubectl get pods -o json` on stdin."""
import json
import sys
from datetime import datetime


def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


data = json.load(sys.stdin)
items = data.get("items", [data])
out = []
for p in items:
    ready = [c for c in p["status"].get("conditions", []) if c["type"] == "Ready" and c["status"] == "True"]
    if ready:
        secs = (ts(ready[0]["lastTransitionTime"]) - ts(p["metadata"]["creationTimestamp"])).total_seconds()
        out.append(secs)
        print(f"{p['metadata']['name']}  created {p['metadata']['creationTimestamp']}  "
              f"ready {ready[0]['lastTransitionTime']}  cold start {secs:.0f}s")
if out:
    print(f"RUN_MAX_SECONDS {max(out):.0f}")
