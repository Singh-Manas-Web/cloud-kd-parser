# Use of AI tools

| Tool | What I used it for | How I checked the result |
|---|---|---|
| Claude (Anthropic) | Explaining the assignment and planning the work; first drafts of the labelling worker, `clean.py`, training/evaluation scripts, FastAPI service, Dockerfiles, Kubernetes manifests, Makefile, experiment scripts, CI workflow and unit tests; the subnet and NACL calculation; the structure and wording of the report | I ran every step myself on my own laptop (Windows 11 + WSL2, Docker Desktop, k3d) and checked each output before moving on; unit tests and the quality gate run in CI; `nacl_sim.py --check` gives 6/6; I recomputed the subnet table and the cost arithmetic by hand; every number in the report comes from a file in `results/` produced on my machine |

## Problems I hit and fixed while running the pipeline
- WSL2 and Docker Desktop setup on Windows, including the Docker socket permission error (added my user to the `docker` group).
- `kubectl` could not reach the k3d API server through `host.docker.internal` from WSL; fixed by giving the cluster a fixed API address (`127.0.0.1:6550`) in `cluster/k3d.yaml`.
- Python 3.14 in Ubuntu was too new for PyTorch 2.5.1; installed Python 3.11 with `uv`.
- Repeated network "connection reset" errors during `pip` installs and GitHub Release uploads; fixed with more pip retries and a lower MTU on the WSL network interface.
- The gitleaks GitHub Action failed on the very first push (it scans from the parent of the root commit); replaced it with the gitleaks CLI scanning the whole history.

## What I verified by hand
- Teacher replies are stored unedited (`teacher_raw`); only teacher outputs were used to train the student.
- The counts table adds up: 3,000 = 4 + 1 + 0 + 117 + 48 + 2,830.
- The GitHub Release files match `model.sha256` (`sha256sum -c`: all OK).
- The CI run on the untrained model fails at the quality gate, and the run on model-v1 passes.
