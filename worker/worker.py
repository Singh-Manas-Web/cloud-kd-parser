"""Teacher-labelling worker (Task 1).

Environment:
  SHARD_INDEX, SHARD_COUNT   this worker takes line numbers i (from 0) with i % SHARD_COUNT == SHARD_INDEX
  S3_ENDPOINT                e.g. http://seaweedfs.data.svc.cluster.local:8333
  AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY   from the Kubernetes Secret s3-credentials
  OLLAMA_URL                 e.g. http://host.k3d.internal:11434
  PROMPT_FILE                default /prompt/teacher_prompt.txt (ConfigMap)
  INPUT_BUCKET / INPUT_KEY   default datasets / commands_pool.jsonl
  OUTPUT_BUCKET / OUTPUT_PREFIX   default datasets / teacher/   -> datasets/teacher/shard-<i>.jsonl
  CHECKPOINT_EVERY           re-upload the shard object every N new records (default 20)

Writes one line per command: {"id": ..., "text": ..., "teacher_raw": <exact teacher reply>}.
The worker is resumable: on restart it downloads its own shard object and skips ids already done.
"""
import json
import os
import sys
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from teacher import ask_teacher, load_prompt  # noqa: E402


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 10, "mode": "standard"}),
    )


def select_shard(lines, index, count):
    """Return the records whose line number (from 0) leaves remainder `index` when divided by `count`."""
    return [json.loads(line) for i, line in enumerate(lines) if i % count == index]


def read_existing(s3, bucket, key):
    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return []
        raise
    return [line for line in body.splitlines() if line.strip()]


def upload(s3, bucket, key, out_lines):
    s3.put_object(Bucket=bucket, Key=key, Body=("\n".join(out_lines) + "\n").encode("utf-8"))


def main():
    index = int(os.environ["SHARD_INDEX"])
    count = int(os.environ["SHARD_COUNT"])
    if not 0 <= index < count:
        sys.exit(f"bad shard: SHARD_INDEX={index} SHARD_COUNT={count}")
    ollama_url = os.environ.get("OLLAMA_URL", "http://host.k3d.internal:11434")
    template = load_prompt(os.environ.get("PROMPT_FILE", "/prompt/teacher_prompt.txt"))
    in_bucket = os.environ.get("INPUT_BUCKET", "datasets")
    in_key = os.environ.get("INPUT_KEY", "commands_pool.jsonl")
    out_bucket = os.environ.get("OUTPUT_BUCKET", "datasets")
    out_key = os.environ.get("OUTPUT_PREFIX", "teacher/") + f"shard-{index}.jsonl"
    every = int(os.environ.get("CHECKPOINT_EVERY", "20"))

    s3 = s3_client()
    pool = s3.get_object(Bucket=in_bucket, Key=in_key)["Body"].read().decode("utf-8")
    lines = [line for line in pool.splitlines() if line.strip()]
    mine = select_shard(lines, index, count)

    out_lines = read_existing(s3, out_bucket, out_key)
    done = {json.loads(line)["id"] for line in out_lines}
    todo = [r for r in mine if r["id"] not in done]
    print(f"shard {index}/{count}: {len(mine)} commands assigned, {len(done)} already done, "
          f"{len(todo)} to go -> s3://{out_bucket}/{out_key}", flush=True)

    start = time.time()
    for n, rec in enumerate(todo, 1):
        reply = ask_teacher(ollama_url, template, rec["text"])
        out_lines.append(json.dumps({"id": rec["id"], "text": rec["text"], "teacher_raw": reply},
                                    ensure_ascii=False))
        if n % every == 0 or n == len(todo):
            upload(s3, out_bucket, out_key, out_lines)
            rate = (time.time() - start) / n
            eta_min = rate * (len(todo) - n) / 60
            print(f"shard {index}: {len(out_lines)}/{len(mine)} done, {rate:.1f}s per command, "
                  f"ETA {eta_min:.0f} min (last id {rec['id']})", flush=True)
    if not todo:
        upload(s3, out_bucket, out_key, out_lines)
    print(f"shard {index}: finished, {len(out_lines)} records in s3://{out_bucket}/{out_key}", flush=True)


if __name__ == "__main__":
    main()
