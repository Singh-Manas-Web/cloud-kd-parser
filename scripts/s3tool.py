"""Tiny S3 helper for SeaweedFS (laptop side).

Credentials: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY from the environment, otherwise
S3_ACCESS_KEY / S3_SECRET_KEY from the untracked .env file. Endpoint: S3_ENDPOINT
(default http://localhost:8333, the k3d port mapping of the SeaweedFS NodePort).

  python scripts/s3tool.py mb datasets models
  python scripts/s3tool.py put data/commands_pool.jsonl s3://datasets/commands_pool.jsonl
  python scripts/s3tool.py put-dir models/v1 s3://models/v1/
  python scripts/s3tool.py get s3://datasets/v1/train.sha256 -
  python scripts/s3tool.py get-dir s3://datasets/teacher/ data/teacher
  python scripts/s3tool.py ls s3://models/
"""
import os
import sys
import time
from pathlib import Path

import boto3
from botocore.config import Config


def _load_env_file():
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)


def client():
    _load_env_file()
    key = os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("S3_ACCESS_KEY")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("S3_SECRET_KEY")
    if not key or not secret:
        sys.exit("No S3 credentials: run scripts/make_secrets.sh first (creates .env)")
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT", "http://localhost:8333"),
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 10, "mode": "standard"}),
    )


def split(uri):
    assert uri.startswith("s3://"), f"expected s3://bucket/key, got {uri}"
    bucket, _, key = uri[5:].partition("/")
    return bucket, key


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    cmd, args = argv[1], argv[2:]
    s3 = client()
    if cmd == "wait":  # wait until the S3 gateway answers
        for _ in range(60):
            try:
                s3.list_buckets()
                print("S3 is up")
                return
            except Exception:  # noqa: BLE001
                time.sleep(3)
        sys.exit("S3 did not come up")
    elif cmd == "mb":
        existing = {b["Name"] for b in s3.list_buckets().get("Buckets", [])}
        for b in args:
            if b in existing:
                print(f"bucket {b} exists")
            else:
                s3.create_bucket(Bucket=b)
                print(f"created bucket {b}")
    elif cmd == "put":
        bucket, key = split(args[1])
        s3.upload_file(args[0], bucket, key)
        print(f"uploaded {args[0]} -> {args[1]}")
    elif cmd == "put-dir":
        bucket, prefix = split(args[1])
        for p in sorted(Path(args[0]).iterdir()):
            if p.is_file():
                s3.upload_file(str(p), bucket, prefix + p.name)
                print(f"uploaded {p} -> s3://{bucket}/{prefix}{p.name}")
    elif cmd == "get":
        bucket, key = split(args[0])
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        if args[1] == "-":
            sys.stdout.write(body.decode())
        else:
            Path(args[1]).parent.mkdir(parents=True, exist_ok=True)
            Path(args[1]).write_bytes(body)
            print(f"downloaded {args[0]} -> {args[1]}")
    elif cmd == "get-dir":
        bucket, prefix = split(args[0])
        out = Path(args[1])
        out.mkdir(parents=True, exist_ok=True)
        for obj in s3.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", []):
            name = obj["Key"][len(prefix):]
            if name and "/" not in name:
                s3.download_file(bucket, obj["Key"], str(out / name))
                print(f"downloaded s3://{bucket}/{obj['Key']} -> {out / name}")
    elif cmd == "ls":
        if not args:
            for b in s3.list_buckets().get("Buckets", []):
                print(b["Name"])
            return
        bucket, prefix = split(args[0])
        for obj in s3.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", []):
            print(f"{obj['Size']:>12}  {obj['LastModified']:%Y-%m-%d %H:%M:%S}  s3://{bucket}/{obj['Key']}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
