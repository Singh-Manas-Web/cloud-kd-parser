#!/usr/bin/env bash
# Task 3: run the service container with 1 CPU and 1 GiB, send 50 sequential requests, record peak memory.
set -uo pipefail
cd "$(dirname "$0")/.."
source .env
OUT=results/task3; mkdir -p "$OUT"
docker rm -f kd-limit >/dev/null 2>&1
docker run -d --name kd-limit --cpus=1 --memory=1g --network k3d-kd -p 8000:8000 \
  -e MODEL_URI=s3://models/v1/ -e MODEL_VERSION=v1 -e S3_ENDPOINT=http://k3d-kd-server-0:30833 \
  -e MAX_NEW_TOKENS=64 -e AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" -e AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" \
  kd-parser:1.0
echo "waiting for /readyz ..."
until [ "$(curl -s -o /dev/null -w '%{http_code}' localhost:8000/readyz)" = "200" ]; do sleep 2; done
docker inspect kd-limit --format 'NanoCpus={{.HostConfig.NanoCpus}} Memory={{.HostConfig.Memory}}' | tee "$OUT/limits.txt"
( while true; do docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}' kd-limit; sleep 1; done ) \
  > "$OUT/docker_stats.txt" 2>/dev/null &
SAMPLER=$!
.venv/bin/python - <<'PY' | tee "$OUT/requests_50.txt"
import json, time, urllib.request
texts = [json.loads(l)["text"] for l in open("data/validation.jsonl")][:50]
ok = 0
for i, t in enumerate(texts, 1):
    req = urllib.request.Request("http://localhost:8000/parse", data=json.dumps({"text": t}).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            code, body = r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        code, body = e.code, e.read().decode()
    ok += code == 200
    print(f"{i:2d} HTTP {code} {time.time()-t0:5.2f}s {body}")
print(f"{ok}/50 returned HTTP 200")
PY
sleep 2; kill $SAMPLER
echo "OOMKilled=$(docker inspect kd-limit --format '{{.State.OOMKilled}}') Status=$(docker inspect kd-limit --format '{{.State.Status}}')" | tee "$OUT/oom.txt"
.venv/bin/python - "$OUT/docker_stats.txt" <<'PY' | tee "$OUT/peak_memory.txt"
import re, sys
units = {"B": 1/2**20, "KiB": 1/1024, "MiB": 1, "GiB": 1024}
peak = 0.0
for line in open(sys.argv[1]):
    m = re.search(r"([\d.]+)(B|KiB|MiB|GiB) /", line)
    if m:
        peak = max(peak, float(m.group(1)) * units[m.group(2)])
print(f"peak memory during the 50 requests: {peak:.1f} MiB (limit 1024 MiB)")
PY
docker logs kd-limit > "$OUT/container.log" 2>&1
docker image ls kd-parser:1.0 | tee "$OUT/image_size.txt"
docker rm -f kd-limit >/dev/null
