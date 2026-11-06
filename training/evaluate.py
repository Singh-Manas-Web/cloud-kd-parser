"""Run a model on validation.jsonl, write raw predictions, and score them with tools/score.py.

  python training/evaluate.py --model models/v1 --out results/student_v1_validation_predictions.jsonl \
      --report results/student_v1_validation.json
  python training/evaluate.py --model EleutherAI/pythia-70m ...      # the original, untrained Pythia-70M
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "service"))
from inference import Parser  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="local model directory or a Hugging Face id")
    ap.add_argument("--revision", default=None, help="Hugging Face revision (for hub ids)")
    ap.add_argument("--gold", default=str(REPO / "data" / "validation.jsonl"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", default=None)
    ap.add_argument("--min-validity", default=None, help="passed through to score.py")
    ap.add_argument("--max-new-tokens", type=int, default=int(os.environ.get("MAX_NEW_TOKENS", "64")))
    args = ap.parse_args()

    revision = args.revision or ("step143000" if args.model == "EleutherAI/pythia-70m" else None)
    parser = Parser(args.model, max_new_tokens=args.max_new_tokens, threads=os.cpu_count(), revision=revision)
    rows = [json.loads(line) for line in open(args.gold, encoding="utf-8") if line.strip()]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with open(args.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"id": r["id"], "prediction": parser.generate(r["text"])}, ensure_ascii=False) + "\n")
    print(f"{len(rows)} predictions from {args.model} in {time.time() - t0:.1f}s -> {args.out}")

    cmd = [sys.executable, str(REPO / "tools" / "score.py"), args.out, args.gold]
    if args.report:
        cmd += ["--out", args.report]
    if args.min_validity:
        cmd += ["--min-validity", str(args.min_validity)]
    sys.exit(subprocess.run(cmd).returncode)


if __name__ == "__main__":
    main()
