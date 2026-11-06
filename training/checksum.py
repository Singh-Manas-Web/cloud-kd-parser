"""SHA-256 checksums of model files, in `sha256sum` format (verify with: sha256sum -c model.sha256).

  python training/checksum.py write models/v1
  python training/checksum.py verify models/v1
"""
import hashlib
import sys
from pathlib import Path

NAME = "model.sha256"


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_checksums(model_dir):
    model_dir = Path(model_dir)
    files = sorted(p for p in model_dir.iterdir() if p.is_file() and p.name != NAME)
    lines = [f"{file_sha256(p)}  {p.name}" for p in files]
    (model_dir / NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines


def verify_checksums(model_dir):
    model_dir = Path(model_dir)
    ok = True
    for line in (model_dir / NAME).read_text().splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            good = file_sha256(model_dir / name.strip()) == digest
            ok &= good
            print(f"{name.strip()}: {'OK' if good else 'FAILED'}")
    return ok


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("write", "verify"):
        sys.exit(__doc__)
    if sys.argv[1] == "write":
        print("\n".join(write_checksums(sys.argv[2])))
    else:
        sys.exit(0 if verify_checksums(sys.argv[2]) else 1)
