"""Checks a raw model output against data/schema.json. Standard library only."""
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_schema(path=None):
    candidates = [path, os.environ.get("SCHEMA_PATH"), HERE / "schema.json", HERE.parent / "data" / "schema.json"]
    for c in candidates:
        if c and Path(c).exists():
            return json.loads(Path(c).read_text(encoding="utf-8"))
    raise FileNotFoundError("schema.json not found")


def validate_output(raw, schema):
    """Return the parsed four-key dict if `raw` is a valid output, otherwise None."""
    try:
        obj = json.loads(raw)
    except (TypeError, ValueError):
        return None
    keys = schema["keys"]
    if not isinstance(obj, dict) or len(obj) != len(keys) or set(obj) != set(keys):
        return None
    if not isinstance(obj["intent"], str) or obj["intent"] not in schema["intents"]:
        return None
    for slot in keys:
        if slot != "intent" and obj[slot] is not None and not isinstance(obj[slot], str):
            return None
    return {k: obj[k] for k in keys}
