# Use of AI tools

> Draft. Edit this so it describes exactly what you did.

| Tool | Used for | How I checked the output |
|---|---|---|
| Claude (Anthropic) | Explaining the assignment; first drafts of the worker, clean.py, training/evaluation scripts, FastAPI service, Dockerfiles, Kubernetes manifests, Makefile, CI workflow and unit tests; the subnet calculation | Ran every script myself on my cluster; unit tests in CI; `nacl_sim.py --check` on the sample packets; recomputed the subnet table by hand; compared `score.py` reports with the numbers in my report; read the manifests against the Kubernetes documentation linked in the handout |
| … | … | … |

## What I changed or fixed myself
- …

## What I verified by hand
- The teacher replies are stored unedited (`teacher_raw`), and only teacher outputs are used for training.
- The counts table adds up (input = a + b + c + d + duplicates + kept).
- All measurements in the report come from files in `results/`.
