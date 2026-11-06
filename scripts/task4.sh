#!/usr/bin/env bash
# Task 4 / Task 7 experiments. Each writes its evidence to results/task4/<name>/.
#   bash scripts/task4.sh endpoints | hpa | rollout | recovery | coldstart | lb
set -uo pipefail
cd "$(dirname "$0")/.."
EXP="${1:?usage: task4.sh endpoints|hpa|rollout|recovery|coldstart|lb}"
OUT="results/task4/$EXP"; mkdir -p "$OUT"
HOST="${HOST:-http://localhost:8080}"
K="kubectl -n app"
LOCUST=".venv/bin/locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --host $HOST"
stamp() { date '+%H:%M:%S'; }
locust_bg() {  # run-time csv-prefix
  LOADTEST_HEADERS_OUT="$OUT/headers.json" $LOCUST --run-time "$1" --csv "$OUT/$2" > "$OUT/locust_output.txt" 2>&1 &
  LOCUST_PID=$!
}
watch_bg() {  # interval command...
  local iv=$1; shift
  ( while true; do echo "== $(stamp)"; "$@"; sleep "$iv"; done ) > "$OUT/watch.txt" 2>&1 &
  WATCH_PID=$!
}
set_min() { $K patch hpa parser --type merge -p "{\"spec\":{\"minReplicas\":$1}}"; }
wait_ready() {  # n
  until [ "$($K get deploy parser -o jsonpath='{.status.readyReplicas}')" = "$1" ] && \
        [ "$($K get deploy parser -o jsonpath='{.status.replicas}')" = "$1" ]; do sleep 3; done
}
summary() { .venv/bin/python scripts/task7_summary.py --stats "$OUT/${1}_stats.csv" --headers "$OUT/headers.json" | tee "$OUT/summary.txt"; }

case "$EXP" in
endpoints)  # Service has no ready endpoints while the model is loading
  set_min 1; $K scale deploy parser --replicas=1 >/dev/null; wait_ready 1
  echo "$(stamp) deleting the Pod; the new Pod must not appear in the endpoints until /readyz is 200"
  $K delete pods -l app=parser --wait=false
  for i in $(seq 1 40); do echo "== $(stamp)"; $K get pods -l app=parser -o wide; $K get endpoints parser; sleep 2; done | tee "$OUT/endpoints_during_load.txt"
  ;;
hpa)  # scale 1 -> 2 under load and back to 1
  set_min 1; echo "$(stamp) waiting for 1 replica"; wait_ready 1
  watch_bg 5 bash -c "$K get hpa parser --no-headers; $K get deploy parser --no-headers; kubectl top pods -n app --no-headers 2>/dev/null"
  sleep 15; locust_bg 4m hpa; wait $LOCUST_PID
  echo "$(stamp) load finished, waiting for scale-down"; sleep 150
  kill $WATCH_PID; $K describe hpa parser > "$OUT/describe_hpa.txt"
  grep -E "^parser" "$OUT/watch.txt" | head -100; tail -15 "$OUT/describe_hpa.txt"; summary hpa
  ;;
rollout)  # v1 -> v2 under load, then rollout undo
  set_min 2; wait_ready 2
  $K rollout history deploy/parser > "$OUT/history_before.txt"
  watch_bg 3 bash -c "$K get pods -l app=parser --no-headers; $K get rs --no-headers"
  locust_bg 6m rollout; sleep 30
  echo "$(stamp) update to v2" | tee -a "$OUT/steps.txt"
  $K set env deploy/parser MODEL_VERSION=v2 MODEL_URI=s3://models/v2/
  $K rollout status deploy/parser --timeout=300s | tee -a "$OUT/steps.txt"
  sleep 40; curl -s -i -X POST "$HOST/parse" -H 'Content-Type: application/json' -d '{"text":"what time is it in tokyo"}' | tee "$OUT/after_update.txt"
  echo; echo "$(stamp) rollout undo" | tee -a "$OUT/steps.txt"
  $K rollout undo deploy/parser
  $K rollout status deploy/parser --timeout=300s | tee -a "$OUT/steps.txt"
  sleep 20; curl -s -i -X POST "$HOST/parse" -H 'Content-Type: application/json' -d '{"text":"what time is it in tokyo"}' | tee "$OUT/after_rollback.txt"
  echo; wait $LOCUST_PID; kill $WATCH_PID
  $K rollout history deploy/parser > "$OUT/history_after.txt"; set_min 1; summary rollout
  ;;
recovery)  # delete one Pod under load
  set_min 2; wait_ready 2
  watch_bg 2 bash -c "$K get deploy parser --no-headers; $K get pods -l app=parser --no-headers"
  locust_bg 3m recovery; sleep 40
  victim=$($K get pods -l app=parser -o jsonpath='{.items[0].metadata.name}')
  echo "$(stamp) deleting $victim" | tee "$OUT/steps.txt"
  $K delete pod "$victim" --wait=false | tee -a "$OUT/steps.txt"
  wait $LOCUST_PID; kill $WATCH_PID
  $K get deploy,pods -l app=parser | tee -a "$OUT/steps.txt"; set_min 1; summary recovery
  ;;
coldstart)  # delete all Pods, measure creation -> Ready, three runs
  : > "$OUT/coldstart.txt"
  for run in 1 2 3; do
    echo "### run $run $(stamp)" | tee -a "$OUT/coldstart.txt"
    $K delete pods -l app=parser --wait=true >/dev/null
    sleep 2
    pods=$($K get pods -l app=parser -o go-template='{{range .items}}{{if not .metadata.deletionTimestamp}}{{.metadata.name}} {{end}}{{end}}')
    $K wait --for=condition=Ready pod $pods --timeout=600s >/dev/null
    $K get pods $pods -o json | .venv/bin/python scripts/pod_times.py | tee -a "$OUT/coldstart.txt"
    for p in $pods; do $K logs "$p" > "$OUT/run${run}_${p}.log"; done
    grep -h -iE "download|ready" "$OUT"/run${run}_*.log | head -12 | tee -a "$OUT/coldstart.txt"
  done
  .venv/bin/python - "$OUT/coldstart.txt" <<'PY' | tee -a "$OUT/coldstart.txt"
import re, statistics, sys
runs = [int(x) for x in re.findall(r"RUN_MAX_SECONDS (\d+)", open(sys.argv[1]).read())]
print(f"cold-start times (s): {runs}; median {statistics.median(runs):.0f}s")
PY
  ;;
lb)  # exactly two Ready replicas, the standard load test, per-Pod CPU/memory (also Task 7)
  set_min 2; wait_ready 2
  $K get pods -l app=parser -o wide | tee "$OUT/pods.txt"
  ( while true; do echo "== $(stamp)"; kubectl top pods -n app --no-headers; sleep 5; done ) > "$OUT/top_pods.txt" 2>&1 &
  TOP=$!
  LOADTEST_HEADERS_OUT=results/loadtest_headers.json $LOCUST --run-time 2m --csv results/loadtest 2>&1 | tee "$OUT/locust_output.txt"
  kill $TOP; cp results/loadtest_stats.csv results/loadtest_headers.json "$OUT/"
  set_min 1
  .venv/bin/python scripts/task7_summary.py --stats results/loadtest_stats.csv --headers results/loadtest_headers.json \
      --top "$OUT/top_pods.txt" --replicas 2 --coldstart results/task4/coldstart/coldstart.txt | tee results/task7_summary.md
  ;;
*) echo "unknown experiment $EXP"; exit 1 ;;
esac
