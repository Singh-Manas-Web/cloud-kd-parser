"""Downloads the model and tokenizer from S3-compatible object storage (SeaweedFS)."""
import hashlib
import logging
import os
import time
from pathlib import Path

log = logging.getLogger("parser.storage")


def parse_uri(uri):
    if not uri.startswith("s3://"):
        raise ValueError(f"MODEL_URI must look like s3://bucket/prefix/, got {uri!r}")
    bucket, _, prefix = uri[5:].partition("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return bucket, prefix


def verify_checksums(dest):
    sums = Path(dest) / "model.sha256"
    if not sums.exists():
        log.warning("no model.sha256 next to the model; skipping checksum verification")
        return
    for line in sums.read_text().splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        name = name.lstrip("*").strip()
        actual = hashlib.sha256((Path(dest) / name).read_bytes()).hexdigest()
        if actual != digest:
            raise RuntimeError(f"checksum mismatch for {name}")
    log.info("all model files match model.sha256")


def download_model(uri, endpoint, dest):
    import boto3
    from botocore.config import Config

    bucket, prefix = parse_uri(uri)
    s3 = boto3.client(
        "s3", endpoint_url=endpoint, region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 5, "mode": "standard"}),
    )  # credentials: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY, injected from a Kubernetes Secret
    t0 = time.time()
    log.info("downloading model from %s (endpoint %s) to %s", uri, endpoint, dest)
    objects = s3.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", [])
    if not objects:
        raise RuntimeError(f"no objects found under {uri}")
    os.makedirs(dest, exist_ok=True)
    total = 0
    for obj in objects:
        name = obj["Key"][len(prefix):]
        if not name or "/" in name:
            continue
        s3.download_file(bucket, obj["Key"], os.path.join(dest, name))
        total += obj["Size"]
        log.info("  downloaded s3://%s/%s (%.1f MB)", bucket, obj["Key"], obj["Size"] / 1e6)
    log.info("model download finished: %.1f MB in %.1fs", total / 1e6, time.time() - t0)
    verify_checksums(dest)
    return dest
