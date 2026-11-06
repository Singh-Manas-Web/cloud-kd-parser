"""Task 7 numbers from the Locust and kubectl outputs, with every step of the cost and SLO arithmetic."""
import argparse
import csv
import json
import re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--stats", required=True)
ap.add_argument("--headers", default=None)
ap.add_argument("--top", default=None)
ap.add_argument("--coldstart", default=None)
ap.add_argument("--replicas", type=int, default=2)
ap.add_argument("--cpu-limit", type=float, default=1.0, help="vCPU limit per replica")
ap.add_argument("--mem-limit-gib", type=float, default=1.0, help="memory limit per replica (GiB)")
ap.add_argument("--slo", type=float, default=99.0, help="success-rate target in percent")
ap.add_argument("--rate-card", default="data/rate_card.json")
a = ap.parse_args()

row = next(r for r in csv.DictReader(open(a.stats)) if r["Name"] == "Aggregated")
n, fails = int(row["Request Count"]), int(row["Failure Count"])
rps, p50, p95 = float(row["Requests/s"]), float(row["50%"]), float(row["95%"])
err = 100 * fails / n if n else 0.0
print("## Load test (Locust, 4 users, 2 min)")
print(f"- requests {n}, failures {fails}, error rate {err:.2f}%")
print(f"- p50 latency {p50:.0f} ms, p95 latency {p95:.0f} ms")
print(f"- throughput {rps:.2f} requests/s")

if a.headers and Path(a.headers).exists():
    h = json.load(open(a.headers))
    total = sum(h["per_replica"].values()) or 1
    print("\n## Successful requests per replica (X-Served-By)")
    for pod, c in h["per_replica"].items():
        print(f"- {pod}: {c} ({100 * c / total:.1f}%)")
    print(f"- per model version: {h['per_model_version']}")

if a.top and Path(a.top).exists():
    cpu, mem = {}, {}
    for line in open(a.top):
        m = re.match(r"(\S+)\s+(\d+)m\s+(\d+)Mi", line)
        if m:
            cpu.setdefault(m[1], []).append(int(m[2]))
            mem.setdefault(m[1], []).append(int(m[3]))
    print("\n## Pod resources during the test (kubectl top pods, every 5 s)")
    for pod in cpu:
        print(f"- {pod}: CPU avg {sum(cpu[pod]) / len(cpu[pod]):.0f}m / max {max(cpu[pod])}m; "
              f"memory avg {sum(mem[pod]) / len(mem[pod]):.0f}Mi / max {max(mem[pod])}Mi")

if a.coldstart and Path(a.coldstart).exists():
    m = re.findall(r"cold-start times.*", open(a.coldstart).read())
    if m:
        print(f"\n## Cold start\n- {m[-1]}")

rc = json.load(open(a.rate_card))
per_replica = a.cpu_limit * rc["vcpu_hour"] + a.mem_limit_gib * rc["gib_memory_hour"]
hourly = a.replicas * per_replica
per_hour = rps * 3600
print("\n## Cost per 1,000 requests (rate_card.json, INR)")
print(f"1. one replica per hour = {a.cpu_limit} vCPU x {rc['vcpu_hour']} + {a.mem_limit_gib} GiB x "
      f"{rc['gib_memory_hour']} = {per_replica:.4f} INR/h")
print(f"2. all running replicas = {a.replicas} x {per_replica:.4f} = {hourly:.4f} INR/h")
print(f"3. requests served per hour = {rps:.4f} req/s x 3600 = {per_hour:.1f} req/h")
if per_hour:
    print(f"4. cost per 1,000 requests = {hourly:.4f} / {per_hour:.1f} x 1000 = {hourly / per_hour * 1000:.4f} INR")

budget = (100 - a.slo) / 100 * n
print(f"\n## SLO: {a.slo:g}% of /parse requests return HTTP 200 within 30 s, window = one standard load-test run")
print(f"- error budget = {100 - a.slo:g}% x {n} requests = {budget:.1f} requests")
print(f"- used: {fails} failed requests = {100 * fails / budget if budget else 0:.1f}% of the budget")
