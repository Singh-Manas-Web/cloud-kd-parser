"""Clean the teacher shard outputs into datasets/v1/train.jsonl (Task 1, step 6).

  python worker/clean.py --shards-dir data/teacher --out-dir data/v1            # local files only
  python worker/clean.py --s3 --shards-dir data/teacher --out-dir data/v1       # download shards from
                                                                                # datasets/teacher/, upload v1/

Each record is checked in this order and counted under the FIRST reason it fails:
  (a) teacher_raw is not valid JSON
  (b) not a JSON object whose keys are exactly intent, date, time, place
  (c) intent is not one of the eight intents
  (d) a slot (date/time/place) is neither null nor a non-empty string that appears in the command
      (case-insensitive substring match)
Then (e) duplicate commands among the surviving records are removed (same text after lower-casing
and trimming; the record with the smallest id is kept). Output is sorted by id and written
deterministically, so re-running on the same shards always gives the same SHA-256.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

KEYS = ("intent", "date", "time", "place")
SLOTS = ("date", "time", "place")
REPO = Path(__file__).resolve().parent.parent


def load_intents(schema_path=None):
    path = Path(schema_path) if schema_path else REPO / "data" / "schema.json"
    if path.exists():
        return set(json.loads(path.read_text(encoding="utf-8"))["intents"])
    return {"alarm_set", "alarm_query", "calendar_set", "calendar_query", "calendar_remove",
            "weather_query", "datetime_query", "recommendation_events"}


def reject_reason(text, raw, intents):
    """Return None if the record is good, otherwise 'a', 'b', 'c' or 'd'."""
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return "a"
    if not isinstance(obj, dict) or set(obj.keys()) != set(KEYS) or len(obj) != 4:
        return "b"
    if not isinstance(obj["intent"], str) or obj["intent"] not in intents:
        return "c"
    lowered = text.lower()
    for slot in SLOTS:
        value = obj[slot]
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip() or value.strip().lower() not in lowered:
            return "d"
    return None


def canonical_target(raw):
    """The teacher's own JSON content, re-serialised with a fixed key order (used as training target)."""
    obj = json.loads(raw)
    return json.dumps({k: obj[k] for k in KEYS}, ensure_ascii=False)


def clean(records, intents):
    """records: list of dicts with id, text, teacher_raw. Returns (kept_records, counts)."""
    counts = {"input": len(records), "a_invalid_json": 0, "b_wrong_keys": 0, "c_bad_intent": 0,
              "d_bad_slot": 0, "e_duplicates": 0, "kept": 0}
    name = {"a": "a_invalid_json", "b": "b_wrong_keys", "c": "c_bad_intent", "d": "d_bad_slot"}
    survivors = []
    for rec in records:
        reason = reject_reason(rec["text"], rec["teacher_raw"], intents)
        if reason:
            counts[name[reason]] += 1
        else:
            survivors.append(rec)
    survivors.sort(key=lambda r: r["id"])
    seen, kept = set(), []
    for rec in survivors:
        key = rec["text"].strip().lower()
        if key in seen:
            counts["e_duplicates"] += 1
            continue
        seen.add(key)
        kept.append({"id": rec["id"], "text": rec["text"], "teacher_raw": rec["teacher_raw"],
                     "target": canonical_target(rec["teacher_raw"])})
    counts["kept"] = len(kept)
    total = sum(v for k, v in counts.items() if k != "input")
    assert total == counts["input"], "counts do not add up"
    return kept, counts


def coverage(records, pool_path):
    """Check that every pool id appears in exactly one shard output."""
    pool_ids = [json.loads(line)["id"] for line in open(pool_path, encoding="utf-8") if line.strip()]
    seen = {}
    for rec in records:
        seen[rec["id"]] = seen.get(rec["id"], 0) + 1
    missing = [i for i in pool_ids if i not in seen]
    repeated = sorted(i for i, n in seen.items() if n > 1)
    extra = sorted(set(seen) - set(pool_ids))
    return {"pool_ids": len(pool_ids), "ids_in_shards": len(seen), "missing": len(missing),
            "repeated": len(repeated), "unknown": len(extra),
            "missing_examples": missing[:10], "repeated_examples": repeated[:10]}


def read_shards(shards_dir):
    files = sorted(Path(shards_dir).glob("shard-*.jsonl"))
    if not files:
        sys.exit(f"no shard-*.jsonl files in {shards_dir}")
    records = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return files, records


def write_outputs(kept, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept).encode("utf-8")
    (out_dir / "train.jsonl").write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    (out_dir / "train.sha256").write_text(f"{digest}  train.jsonl\n", encoding="utf-8")
    return digest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shards-dir", default="data/teacher")
    ap.add_argument("--out-dir", default="data/v1")
    ap.add_argument("--pool", default=str(REPO / "data" / "commands_pool.jsonl"))
    ap.add_argument("--schema", default=None)
    ap.add_argument("--report", default="results/clean_report.json")
    ap.add_argument("--s3", action="store_true", help="download shards from s3://datasets/teacher/ and "
                                                       "upload outputs to s3://datasets/v1/")
    args = ap.parse_args()

    if args.s3:
        sys.path.insert(0, str(REPO / "scripts"))
        from s3tool import client  # noqa: E402
        s3 = client()
        Path(args.shards_dir).mkdir(parents=True, exist_ok=True)
        for obj in s3.list_objects_v2(Bucket="datasets", Prefix="teacher/").get("Contents", []):
            name = obj["Key"].split("/")[-1]
            if name.startswith("shard-"):
                s3.download_file("datasets", obj["Key"], os.path.join(args.shards_dir, name))
                print(f"downloaded s3://datasets/{obj['Key']}")

    files, records = read_shards(args.shards_dir)
    kept, counts = clean(records, load_intents(args.schema))
    digest = write_outputs(kept, args.out_dir)
    report = {"shard_files": [f.name for f in files],
              "per_shard_records": {f.name: sum(1 for x in f.read_text().splitlines() if x.strip()) for f in files},
              "coverage": coverage(records, args.pool), "counts": counts, "train_sha256": digest,
              "first_1500_last_id": kept[min(1499, len(kept) - 1)]["id"] if kept else None}
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

    if args.s3:
        for name in ("train.jsonl", "train.sha256"):
            s3.upload_file(os.path.join(args.out_dir, name), "datasets", f"v1/{name}")
            print(f"uploaded s3://datasets/v1/{name}")


if __name__ == "__main__":
    main()
