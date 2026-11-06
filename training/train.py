"""Sequence-level knowledge distillation (Task 2): fine-tune Pythia-70M on the teacher's replies.

  python training/train.py --config training/config.yaml               # full run -> models/v1
  python training/train.py --config training/config.yaml --subset 50   # smoke test on the first 50 records

Every training example is
    Command: <the command>
    JSON: <the teacher's JSON reply><eos>
and the loss is computed on the JSON part only (the command part is masked with -100).
"""
import argparse
import csv
import json
import math
import random
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "service"))
sys.path.insert(0, str(REPO / "training"))
from checksum import write_checksums  # noqa: E402
from inference import format_prompt  # noqa: E402


def set_seed(seed):
    import numpy as np
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def check_versions(expected):
    for pkg, want in expected.items():
        if pkg == "python":
            have = f"{sys.version_info.major}.{sys.version_info.minor}"
        else:
            try:
                have = version(pkg)
            except PackageNotFoundError:
                have = "missing"
        if not have.startswith(str(want)):
            print(f"WARNING: {pkg} {have} installed, config.yaml records {want}")


def build_example(tok, rec, max_len):
    target = rec.get("target") or rec["teacher_raw"].strip()
    prompt_ids = tok(format_prompt(rec["text"]))["input_ids"]
    target_ids = tok(" " + target)["input_ids"] + [tok.eos_token_id]
    ids = (prompt_ids + target_ids)[:max_len]
    labels = ([-100] * len(prompt_ids) + target_ids)[:max_len]
    return ids, labels


def collate(batch, pad_id):
    import torch

    width = max(len(ids) for ids, _ in batch)
    input_ids, labels, mask = [], [], []
    for ids, lab in batch:
        pad = width - len(ids)
        input_ids.append(ids + [pad_id] * pad)
        labels.append(lab + [-100] * pad)
        mask.append([1] * len(ids) + [0] * pad)
    return torch.tensor(input_ids), torch.tensor(labels), torch.tensor(mask)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="training/config.yaml")
    ap.add_argument("--subset", type=int, default=0, help="train on the first N records only (quick check)")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, get_linear_schedule_with_warmup

    check_versions(cfg["library_versions"])
    seed = int(cfg["seed"])
    set_seed(seed)  # the seed is fixed in code from config.yaml
    torch.set_num_threads(max(1, torch.get_num_threads()))

    n_records = args.subset or int(cfg["max_train_records"])
    out_dir = REPO / (f"models/subset{args.subset}" if args.subset else cfg["output_dir"])
    loss_csv = REPO / (f"training/loss_subset{args.subset}.csv" if args.subset else cfg["loss_csv"])

    rows = [json.loads(line) for line in open(REPO / cfg["train_file"], encoding="utf-8") if line.strip()]
    records = rows[:n_records]  # the first records of the cleaned, id-ordered dataset
    print(f"training on {len(records)} records ({records[0]['id']} .. {records[-1]['id']}) from {cfg['train_file']}")

    tok = AutoTokenizer.from_pretrained(cfg["base_model"], revision=cfg["base_model_revision"])
    model = AutoModelForCausalLM.from_pretrained(cfg["base_model"], revision=cfg["base_model_revision"])
    model.train()
    max_len = int(cfg["max_seq_length"])
    examples = [build_example(tok, r, max_len) for r in records]

    bs, epochs, lr = int(cfg["batch_size"]), int(cfg["epochs"]), float(cfg["learning_rate"])
    steps_per_epoch = math.ceil(len(examples) / bs)
    total_steps = steps_per_epoch * epochs
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=float(cfg["weight_decay"]))
    sched = get_linear_schedule_with_warmup(opt, int(float(cfg["warmup_ratio"]) * total_steps), total_steps)
    gen = torch.Generator().manual_seed(seed)

    history = []
    t_start = time.time()
    for epoch in range(1, epochs + 1):
        t0 = time.time()
        order = torch.randperm(len(examples), generator=gen).tolist()
        total, batches = 0.0, 0
        for i in range(0, len(order), bs):
            ids, labels, mask = collate([examples[j] for j in order[i:i + bs]], tok.eos_token_id)
            loss = model(input_ids=ids, attention_mask=mask, labels=labels).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), float(cfg["max_grad_norm"]))
            opt.step()
            sched.step()
            opt.zero_grad()
            total += loss.item()
            batches += 1
        history.append((epoch, total / batches, time.time() - t0))
        print(f"epoch {epoch}/{epochs}  train_loss {total / batches:.4f}  ({time.time() - t0:.0f}s)", flush=True)

    loss_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(loss_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "train_loss", "seconds"])
        for e, loss_value, secs in history:
            w.writerow([e, f"{loss_value:.6f}", f"{secs:.1f}"])

    out_dir.mkdir(parents=True, exist_ok=True)
    model.eval()
    model.save_pretrained(out_dir, safe_serialization=True)
    tok.save_pretrained(out_dir)
    info = {"model_version": "subset" if args.subset else cfg["model_version"],
            "base_model": f"{cfg['base_model']}@{cfg['base_model_revision']}",
            "method": "sequence-level knowledge distillation from phi3.5 (Ollama, temperature 0, seed 42)",
            "train_file": cfg["train_file"], "train_records": len(records), "seed": seed, "epochs": epochs,
            "learning_rate": lr, "batch_size": bs, "max_seq_length": max_len,
            "final_train_loss": round(history[-1][1], 6), "training_seconds": round(time.time() - t_start, 1),
            "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    (out_dir / "version.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    sums = write_checksums(out_dir)
    print(f"saved model, tokenizer, version.json and model.sha256 to {out_dir}")
    print("\n".join(sums))
    print(f"loss per epoch -> {loss_csv}")


if __name__ == "__main__":
    main()
