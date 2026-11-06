# Inference service image. Build from the repository root:  docker build -f service/Dockerfile -t kd-parser:1.0 .
# Contains NO model weights: the model is downloaded from object storage at start-up.
FROM python:3.11.11-slim

ENV PIP_RETRIES=20 PIP_DEFAULT_TIMEOUT=60 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false \
    TORCH_THREADS=1

WORKDIR /app
COPY service/requirements.txt .
# CPU-only PyTorch wheel (the default wheels bundle GPU libraries and blow the 2 GB budget), then the rest, all pinned.
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY service/app.py service/inference.py service/storage.py service/validation.py ./
COPY data/schema.json ./schema.json

RUN useradd --uid 1000 --create-home appuser && mkdir -p /tmp/model && chown appuser /tmp/model
USER 1000
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "20"]
