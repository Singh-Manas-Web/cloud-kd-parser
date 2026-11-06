"""Inference service for the distilled command parser (Task 3).

Configuration (environment only):
  MODEL_URI        s3://models/v1/          where the model + tokenizer live
  MODEL_VERSION    v1                        returned in the X-Model-Version header
  S3_ENDPOINT      http://seaweedfs.data.svc.cluster.local:8333
  MAX_NEW_TOKENS   64                        generation budget
  FAULT_INJECT     0|1                       1 = replace the model output with "not json" before validation
Credentials AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY come from a Kubernetes Secret.
"""
import logging
import os
import socket
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from storage import download_model
from validation import load_schema, validate_output

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("parser")

START = time.time()
SCHEMA = load_schema()
MODEL_VERSION = os.environ.get("MODEL_VERSION", "unknown")
SERVED_BY = os.environ.get("POD_NAME") or socket.gethostname()
MODEL_DIR = os.environ.get("MODEL_DIR", "/tmp/model")


class State:
    parser = None
    ready = False


STATE = State()
GENERATE_LOCK = threading.Lock()


def load_model():
    uri = os.environ["MODEL_URI"]
    endpoint = os.environ["S3_ENDPOINT"]
    max_new_tokens = int(os.environ.get("MAX_NEW_TOKENS", "64"))
    delay = 2
    while True:
        try:
            download_model(uri, endpoint, MODEL_DIR)
            from inference import Parser, default_threads

            STATE.parser = Parser(MODEL_DIR, max_new_tokens=max_new_tokens, threads=default_threads())
            STATE.parser.generate("what is the weather in london")  # warm-up
            STATE.ready = True
            log.info("model %s loaded from %s; ready %.1fs after process start", MODEL_VERSION, uri,
                     time.time() - START)
            return
        except Exception as exc:  # noqa: BLE001  keep retrying, e.g. while object storage starts
            log.error("model load failed (%s); retrying in %ss", exc, delay)
            time.sleep(delay)
            delay = min(delay * 2, 30)


@asynccontextmanager
async def lifespan(_app):
    if os.environ.get("SKIP_MODEL_LOAD") != "1":
        threading.Thread(target=load_model, name="model-loader", daemon=True).start()
    yield


app = FastAPI(title="command-parser", lifespan=lifespan)


class ParseRequest(BaseModel):
    text: str


def _headers():
    return {"X-Model-Version": MODEL_VERSION, "X-Served-By": SERVED_BY}


@app.get("/healthz")
async def healthz():
    return {"status": "alive"}


@app.get("/readyz")
async def readyz():
    if STATE.ready:
        return {"status": "ready", "model_version": MODEL_VERSION}
    return JSONResponse({"status": "loading"}, status_code=503)


@app.post("/parse")
def parse(req: ParseRequest):
    if not STATE.ready:
        return JSONResponse({"error": "model_not_ready"}, status_code=503, headers=_headers())
    with GENERATE_LOCK:
        raw = STATE.parser.generate(req.text)
    if os.environ.get("FAULT_INJECT", "0") == "1":
        raw = "not json"
    result = validate_output(raw, SCHEMA)
    if result is None:
        log.warning("invalid model output for %r: %r", req.text, raw)
        return JSONResponse({"error": "invalid_model_output"}, status_code=500, headers=_headers())
    return JSONResponse(result, headers=_headers())
