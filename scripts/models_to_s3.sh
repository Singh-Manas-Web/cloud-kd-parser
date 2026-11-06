#!/usr/bin/env bash
# Puts models v1 and v2 into the "models" bucket. Uses local copies in models/<v>/ when they exist
# (your laptop), otherwise downloads them from the GitHub Release "model-<v>" (fresh clone / marker).
set -euo pipefail
cd "$(dirname "$0")/.."
GH_REPO="${1:-Singh-Manas-Web/cloud-kd-parser}"
PYBIN=.venv/bin/python
for v in v1 v2; do
  src="models/$v"
  if [ ! -f "$src/model.sha256" ]; then
    src=".tmp/release/$v"; mkdir -p "$src"
    base="https://github.com/$GH_REPO/releases/download/model-$v"
    echo "downloading model $v from $base"
    if ! curl -fsSL -o "$src/model.sha256" "$base/model.sha256"; then
      echo "WARNING: no release model-$v found; skipping $v"; continue
    fi
    awk '{print $2}' "$src/model.sha256" | while read -r f; do
      curl -fsSL -o "$src/$f" "$base/$f"
    done
  fi
  $PYBIN training/checksum.py verify "$src"
  $PYBIN scripts/s3tool.py put-dir "$src" "s3://models/$v/"
done
$PYBIN scripts/s3tool.py ls s3://models/
