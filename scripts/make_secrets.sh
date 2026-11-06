#!/usr/bin/env bash
# Creates random S3 credentials (kept only in the untracked file .env) and stores them in
# Kubernetes Secrets. Nothing secret is ever written to the repository.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  python3 - <<'EOF' > .env
import secrets
print(f"S3_ACCESS_KEY={secrets.token_hex(10)}")
print(f"S3_SECRET_KEY={secrets.token_hex(20)}")
EOF
  chmod 600 .env
  echo "Generated new S3 credentials in .env (git-ignored)"
fi
# shellcheck disable=SC1091
source .env

mkdir -p .tmp
python3 - "$S3_ACCESS_KEY" "$S3_SECRET_KEY" > .tmp/s3.json <<'EOF'
import json, sys
print(json.dumps({"identities": [{
    "name": "admin",
    "credentials": [{"accessKey": sys.argv[1], "secretKey": sys.argv[2]}],
    "actions": ["Admin", "Read", "Write", "List", "Tagging"]}]}))
EOF

kubectl apply -f k8s/namespaces.yaml >/dev/null
kubectl -n data create secret generic seaweedfs-s3-config --from-file=s3.json=.tmp/s3.json \
  --dry-run=client -o yaml | kubectl apply -f -
for ns in pipeline app; do
  kubectl -n "$ns" create secret generic s3-credentials \
    --from-literal=AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" \
    --from-literal=AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" \
    --dry-run=client -o yaml | kubectl apply -f -
done
rm -f .tmp/s3.json
echo "Secrets ready in namespaces data, pipeline, app"
