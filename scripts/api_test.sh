#!/usr/bin/env bash
# Task 3 evidence: endpoints, headers, /readyz 503 -> 200, and FAULT_INJECT=1 -> HTTP 500.
set -uo pipefail
cd "$(dirname "$0")/.."
source .env
OUT=results/task3; mkdir -p "$OUT"; LOG="$OUT/api_test.txt"; : > "$LOG"
run() {  # name port fault
  docker rm -f "$1" >/dev/null 2>&1
  docker run -d --name "$1" --network k3d-kd -p "$2":8000 -e MODEL_URI=s3://models/v1/ -e MODEL_VERSION=v1 \
    -e S3_ENDPOINT=http://k3d-kd-server-0:30833 -e MAX_NEW_TOKENS=64 -e FAULT_INJECT="$3" \
    -e AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" -e AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" kd-parser:1.0 >/dev/null
}
run kd-api 8000 0
sleep 3
{ echo "### just after start"; curl -s -i localhost:8000/healthz; echo; curl -s -i localhost:8000/readyz; echo; } >> "$LOG"
until [ "$(curl -s -o /dev/null -w '%{http_code}' localhost:8000/readyz)" = "200" ]; do sleep 2; done
{ echo "### after the model is loaded"; curl -s -i localhost:8000/readyz; echo
  curl -s -i -X POST localhost:8000/parse -H 'Content-Type: application/json' -d '{"text":"set an alarm for seven thirty am tomorrow"}'; echo
  curl -s -i -X POST localhost:8000/parse -H 'Content-Type: application/json' -d '{"text":"what is the weather in london"}'; echo; } >> "$LOG"
run kd-fault 8001 1
until [ "$(curl -s -o /dev/null -w '%{http_code}' localhost:8001/readyz)" = "200" ]; do sleep 2; done
{ echo "### FAULT_INJECT=1"; curl -s -i -X POST localhost:8001/parse -H 'Content-Type: application/json' -d '{"text":"what is the weather in london"}'; echo; } >> "$LOG"
docker logs kd-api > "$OUT/startup_log.txt" 2>&1
docker rm -f kd-api kd-fault >/dev/null
cat "$LOG"
