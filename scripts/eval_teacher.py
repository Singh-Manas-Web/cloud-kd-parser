"""Run the teacher (same prompt and settings as the workers) on labelled or unlabelled commands.

  # quick try on 20 pool commands: prints each reply and the time per command
  python scripts/eval_teacher.py --input data/commands_pool.jsonl --limit 20 --out results/teacher_try20.jsonl

  # full validation run for Task 2 step 6 (writes predictions + score report)
  python scripts/eval_teacher.py --input data/validation.jsonl \
      --out results/teacher_validation_predictions.jsonl --report results/teacher_validation.json

OLLAMA_URL defaults to http://localhost:11434 (the teacher running on the laptop).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "worker"))
from teacher import FORMAT_JSON, MODEL, OPTIONS, ask_teacher, load_prompt  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/validation.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", default=None, help="if set, run tools/score.py and write this report")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--prompt", default=str(REPO / "prompts" / "teacher_prompt.txt"))
    args = ap.parse_args()

    url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    template = load_prompt(args.prompt)
    rows = [json.loads(line) for line in open(args.input, encoding="utf-8") if line.strip()]
    if args.limit:
        rows = rows[: args.limit]
    print(f"teacher={MODEL} options={OPTIONS} format_json={FORMAT_JSON} url={url} n={len(rows)}", flush=True)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    times = []
    with open(args.out, "w", encoding="utf-8") as f:
        for r in rows:
            t0 = time.time()
            reply = ask_teacher(url, template, r["text"])
            times.append(time.time() - t0)
            f.write(json.dumps({"id": r["id"], "prediction": reply}, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{r['id']}  {times[-1]:5.1f}s  {r['text']!r}\n        -> {reply!r}", flush=True)
    avg = sum(times) / len(times)
    print(f"\naverage {avg:.2f}s per command; 3000 commands at this speed with one stream "
          f"= {avg * 3000 / 3600:.1f} h", flush=True)

    if args.report:
        cmd = [sys.executable, str(REPO / "tools" / "score.py"), args.out, args.input, "--out", args.report]
        subprocess.run(cmd, check=False)


if __name__ == "__main__":
    main()
