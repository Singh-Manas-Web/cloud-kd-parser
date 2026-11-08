# Distilled command parser on a local Kubernetes cloud

Cloud Computing (CS3081) mini project. Manas Singh, 230103017.

A 70M-parameter student (EleutherAI/pythia-70m) is trained with **sequence-level knowledge distillation**
on replies from the teacher **phi3.5** (Ollama, temperature 0, seed 42). It turns a short English
command into `{"intent", "date", "time", "place"}`. The student runs as a FastAPI service on a k3d
cluster, with model files kept in SeaweedFS (S3-compatible object storage).

```
commands_pool.jsonl ─► SeaweedFS (datasets) ─► 2 worker Jobs (namespace pipeline) ─► phi3.5 / Ollama
                                   ▲                         │ shard-0.jsonl, shard-1.jsonl
                                   └──── clean.py ◄──────────┘ ─► datasets/v1/train.jsonl (+ sha256)
train.py (CPU) ─► models/v1, models/v2 ─► SeaweedFS (models) + GitHub Release
Ingress (Traefik, :8080) ─► Service ─► Deployment "parser" (namespace app, HPA 1–2) ─► downloads model at start-up
```

## Links

| What | Link |
|---|---|
| **GitHub repository** | https://github.com/Singh-Manas-Web/cloud-kd-parser |
| Final assessed commit | tag [`final`](https://github.com/Singh-Manas-Web/cloud-kd-parser/tree/final) |
| Model v1 (Release assets: model, tokenizer, version.json, model.sha256) | https://github.com/Singh-Manas-Web/cloud-kd-parser/releases/tag/model-v1 |
| Model v2 | https://github.com/Singh-Manas-Web/cloud-kd-parser/releases/tag/model-v2 |
| Untrained Pythia-70M (bad model for the CI gate test) | https://github.com/Singh-Manas-Web/cloud-kd-parser/releases/tag/model-bad |
| CI run passing all four stages (model-v1) | https://github.com/Singh-Manas-Web/cloud-kd-parser/actions/runs/42341969740 |
| CI run failing at the quality gate (untrained model) | https://github.com/Singh-Manas-Web/cloud-kd-parser/actions/runs/42341958991 |

## Submission contents

| Item | Location |
|---|---|
| Report (one section per task, at most 8 pages) | `report/report.pdf` |
| Handwritten reflection (3 pages) | `230103017.pdf` |
| Evidence: logs, score.py outputs, Locust results, command outputs | `results/` |
| Use of AI tools | `AI_USE.md` |
| Model files | GitHub Releases only (never committed to Git) |

## Requirements

Docker, k3d ≥ 5.6, kubectl, Python 3.11 or 3.12 with `venv`, make, curl. For Task 1 only: Ollama with
`phi3.5`. For releases: the GitHub CLI `gh`.

## Build and deploy (fresh clone, three commands)

```bash
git clone https://github.com/Singh-Manas-Web/cloud-kd-parser.git
cd cloud-kd-parser
make up        # cluster, SeaweedFS, buckets, models from the GitHub Release, image, Deployment, smoke test
```
Test it: `curl -s -i -X POST http://localhost:8080/parse -H 'Content-Type: application/json' -d '{"text":"set an alarm for seven am tomorrow"}'`

Or run `make smoke` (one request through the Ingress). Unit tests and lint: `.venv/bin/pip install -r tests/requirements.txt && make test lint`.

Tear down: `make down` (deletes the cluster). Run `make help` to list every target.

## Pipeline commands

| Step | Command |
|---|---|
| Cluster, secrets, storage | `make cluster secrets storage` |
| Teacher labelling (2 workers) | `ollama serve` with `OLLAMA_HOST=0.0.0.0`, then `make label`; progress: `make label-status` |
| Clean the teacher data | `make clean-data` (counts in `results/clean_report.json`) |
| Teacher on validation | `make eval-teacher` |
| Train student v1 / quick check / v2 | `make train`, `make train SUBSET=50`, `make train-v2` |
| Untrained baseline | `make untrained` |
| Models to object storage / Release | `make upload-models`, `make release` |
| Evaluate untrained, v1, v2 | `make eval` |
| Service image | `make service-image` |
| API and fault-injection test | `make api-test` |
| 1 CPU / 1 GiB test | `make limit-test` |
| Deploy | `make deploy` |
| Task 4 experiments | `make exp-endpoints exp-hpa exp-rollout exp-recovery exp-coldstart` |
| Load balancing + Task 7 numbers | `make exp-lb` (writes `results/loadtest_*` and `results/task7_summary.md`) |
| Unit tests / lint | `make test`, `make lint` |
| Subnet + NACL check | `python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check` |

Credentials are generated at deploy time into the untracked `.env` file and stored only in
Kubernetes Secrets. Model weights are never committed. They live in SeaweedFS and in the GitHub
Releases `model-v1` and `model-v2` (verify with `sha256sum -c model.sha256`).

## Layout

`cluster/` k3d config · `k8s/` manifests (data, pipeline, app) · `prompts/` teacher prompt ·
`worker/` labelling worker + clean.py · `training/` config, training, evaluation · `service/` API +
Dockerfile · `tests/` unit tests · `network/` subnets and NACL · `results/` evidence ·
`report/report.pdf`.

Data: SLURP (Bastianelli et al., EMNLP 2020), CC BY 4.0.
