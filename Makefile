# Cloud Computing mini project: distilled command parser on k3d.
# From a fresh clone:   git clone <repo> && cd cloud-kd-parser && make up
SHELL := /bin/bash
CLUSTER    ?= kd
GH_REPO    ?= Singh-Manas-Web/cloud-kd-parser
PY         ?= $(shell command -v python3.11 || command -v python3.12 || command -v python3)
VENV       := .venv
VPY        := $(VENV)/bin/python
SUBSET     ?=
TORCH_VER  := 2.5.1
IMAGE      := kd-parser:1.0
WORKER_IMG := kd-worker:1.0
HOST       ?= http://localhost:8080

.PHONY: up down venv venv-train cluster secrets storage label label-status label-logs clean-data \
        train train-v2 untrained upload-models release models-to-s3 eval eval-teacher service-image \
        deploy smoke loadtest limit-test api-test test lint help

help:
	@grep -E '^[a-z0-9%-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-16s %s\n",$$1,$$2}'

# ---------------------------------------------------------------- whole system
up: venv cluster secrets storage models-to-s3 service-image deploy smoke ## build and deploy everything
	@echo "System is up: curl -s -X POST $(HOST)/parse -H 'Content-Type: application/json' -d '{\"text\":\"what is the weather in london\"}'"

down: ## delete the cluster
	k3d cluster delete $(CLUSTER)

# ---------------------------------------------------------------- python envs
$(VENV)/.host-ok: scripts/requirements.txt
	$(PY) -m venv $(VENV)
	$(VPY) -m pip install -q --upgrade pip
	$(VPY) -m pip install -q -r scripts/requirements.txt
	touch $@
venv: $(VENV)/.host-ok ## laptop-side tools (boto3, locust)

$(VENV)/.train-ok: $(VENV)/.host-ok training/requirements.txt
	$(VPY) -m pip install -q torch==$(TORCH_VER) --index-url https://download.pytorch.org/whl/cpu
	$(VPY) -m pip install -q -r training/requirements.txt
	touch $@
venv-train: $(VENV)/.train-ok ## training/evaluation libraries (CPU PyTorch)

# ---------------------------------------------------------------- Task 1
cluster: ## create the k3d cluster from cluster/k3d.yaml
	@k3d cluster list $(CLUSTER) >/dev/null 2>&1 && echo "cluster $(CLUSTER) exists" || k3d cluster create --config cluster/k3d.yaml
	kubectl apply -f k8s/namespaces.yaml

secrets: ## random S3 credentials -> .env (untracked) -> Kubernetes Secrets
	bash scripts/make_secrets.sh

storage: venv ## SeaweedFS in namespace data, buckets datasets + models, upload the pool
	kubectl apply -f k8s/data/seaweedfs.yaml
	kubectl -n data rollout status deploy/seaweedfs --timeout=300s
	$(VPY) scripts/s3tool.py wait
	$(VPY) scripts/s3tool.py mb datasets models
	$(VPY) scripts/s3tool.py put data/commands_pool.jsonl s3://datasets/commands_pool.jsonl
	$(VPY) scripts/s3tool.py ls s3://datasets/

label: ## build the worker image and start 2 labelling workers in namespace pipeline
	docker build -t $(WORKER_IMG) worker/
	k3d image import $(WORKER_IMG) -c $(CLUSTER)
	kubectl -n pipeline create configmap teacher-prompt --from-file=teacher_prompt.txt=prompts/teacher_prompt.txt \
	  --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -f k8s/pipeline/worker-jobs.yaml
	kubectl -n pipeline get pods -o wide

label-status: venv ## progress of the labelling workers
	kubectl -n pipeline get jobs,pods
	@for i in 0 1; do kubectl -n pipeline logs job/teacher-worker-$$i --tail=1 2>/dev/null; done
	$(VPY) scripts/s3tool.py ls s3://datasets/teacher/

label-logs: ## save worker logs as evidence
	mkdir -p results/task1
	kubectl -n pipeline get jobs,pods -o wide > results/task1/pipeline_pods.txt
	for i in 0 1; do kubectl -n pipeline logs job/teacher-worker-$$i > results/task1/worker-$$i.log; done

clean-data: venv ## download shards, run clean.py, upload datasets/v1/train.jsonl + train.sha256
	$(VPY) worker/clean.py --s3 --shards-dir data/teacher --out-dir data/v1 --report results/clean_report.json

# ---------------------------------------------------------------- Task 2
train: venv-train ## train the student from training/config.yaml (make train SUBSET=50 for a quick check)
	$(VPY) training/train.py --config training/config.yaml $(if $(SUBSET),--subset $(SUBSET),)

train-v2: venv-train ## train model v2 from training/config_v2.yaml
	$(VPY) training/train.py --config training/config_v2.yaml

untrained: venv-train ## export the untrained Pythia-70M (for the comparison and the failing CI run)
	$(VPY) training/export_untrained.py --out models/untrained

upload-models: venv ## upload models/v1 and models/v2 to the models bucket
	$(VPY) scripts/s3tool.py put-dir models/v1 s3://models/v1/
	$(VPY) scripts/s3tool.py put-dir models/v2 s3://models/v2/
	$(VPY) scripts/s3tool.py ls s3://models/

release: ## publish models as GitHub Release assets (needs gh auth)
	gh release create model-v1 models/v1/* --title "Student model v1" --notes "Pythia-70M distilled from phi3.5 (v1). Verify: sha256sum -c model.sha256" || gh release upload model-v1 models/v1/* --clobber
	gh release create model-v2 models/v2/* --title "Student model v2" --notes "Pythia-70M distilled from phi3.5 (v2)" || gh release upload model-v2 models/v2/* --clobber

models-to-s3: venv ## put models v1/v2 into SeaweedFS (local copies, or downloaded from the GitHub Release)
	bash scripts/models_to_s3.sh $(GH_REPO)

eval-teacher: venv ## teacher on validation.jsonl (needs Ollama running)
	$(VPY) scripts/eval_teacher.py --input data/validation.jsonl --out results/teacher_validation_predictions.jsonl --report results/teacher_validation.json

eval: venv-train ## untrained Pythia and student v1/v2 on validation.jsonl
	$(VPY) training/evaluate.py --model EleutherAI/pythia-70m --out results/untrained_validation_predictions.jsonl --report results/untrained_validation.json
	$(VPY) training/evaluate.py --model models/v1 --out results/student_v1_validation_predictions.jsonl --report results/student_v1_validation.json
	$(VPY) training/evaluate.py --model models/v2 --out results/student_v2_validation_predictions.jsonl --report results/student_v2_validation.json

# ---------------------------------------------------------------- Tasks 3-4
service-image: ## build the inference image (no weights) and import it into k3d
	docker build -f service/Dockerfile -t $(IMAGE) .
	docker image ls $(IMAGE)
	k3d image import $(IMAGE) -c $(CLUSTER)

deploy: ## Deployment, Service, Ingress, HPA in namespace app
	kubectl apply -f k8s/app/
	kubectl -n app rollout status deploy/parser --timeout=600s
	kubectl -n app get deploy,pods,svc,ingress,hpa

smoke: ## one request through the Ingress
	@for i in $$(seq 1 30); do curl -sf -o /dev/null -X POST $(HOST)/parse -H 'Content-Type: application/json' -d '{"text":"x"}' && break || sleep 2; done
	curl -s -i -X POST $(HOST)/parse -H 'Content-Type: application/json' -d '{"text":"set an alarm for seven am tomorrow"}'; echo

loadtest: venv ## the standard load test through the Ingress
	mkdir -p results
	-$(VENV)/bin/locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m --host $(HOST) --csv results/loadtest

limit-test: ## Task 3: 50 sequential requests at 1 CPU / 1 GiB, peak memory
	bash scripts/limit_test.sh

api-test: ## Task 3: endpoints, headers, readiness and FAULT_INJECT evidence
	bash scripts/api_test.sh

exp-%: venv ## Task 4/7 experiments: exp-endpoints exp-hpa exp-rollout exp-recovery exp-coldstart exp-lb
	bash scripts/task4.sh $*

# ---------------------------------------------------------------- Task 6 helpers
lint:
	$(VPY) -m ruff check .
test:
	$(VPY) -m pytest -q tests
