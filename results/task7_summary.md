## Load test (Locust, 4 users, 2 min)
- requests 316, failures 0, error rate 0.00%
- p50 latency 1500 ms, p95 latency 2100 ms
- throughput 2.65 requests/s

## Successful requests per replica (X-Served-By)
- parser-67bb49c8d-djx9w: 158 (49.8%)
- parser-67bb49c8d-5fjs6: 159 (50.2%)
- per model version: {'v1': 317}

## Pod resources during the test (kubectl top pods, every 5 s)
- parser-67bb49c8d-5fjs6: CPU avg 955m / max 999m; memory avg 556Mi / max 611Mi
- parser-67bb49c8d-djx9w: CPU avg 965m / max 1001m; memory avg 547Mi / max 611Mi

## Cold start
- cold-start times (s): [20, 24, 30]; median 24s

## Cost per 1,000 requests (rate_card.json, INR)
1. one replica per hour = 1.0 vCPU x 3.5 + 1.0 GiB x 0.45 = 3.9500 INR/h
2. all running replicas = 2 x 3.9500 = 7.9000 INR/h
3. requests served per hour = 2.6536 req/s x 3600 = 9552.9 req/h
4. cost per 1,000 requests = 7.9000 / 9552.9 x 1000 = 0.8270 INR

## SLO: 99% of /parse requests return HTTP 200 within 30 s, window = one standard load-test run
- error budget = 1% x 316 requests = 3.2 requests
- used: 0 failed requests = 0.0% of the budget
