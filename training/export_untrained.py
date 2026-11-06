"""Save the original, untrained Pythia-70M in the same layout as a trained model
(used as the deliberately bad model for the failing CI quality-gate run)."""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "training"))
from checksum import write_checksums  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="models/untrained")
args = ap.parse_args()

from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402

out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
AutoTokenizer.from_pretrained("EleutherAI/pythia-70m", revision="step143000").save_pretrained(out)
AutoModelForCausalLM.from_pretrained("EleutherAI/pythia-70m", revision="step143000").save_pretrained(
    out, safe_serialization=True)
(out / "version.json").write_text(json.dumps({"model_version": "untrained",
                                               "base_model": "EleutherAI/pythia-70m@step143000"}, indent=2) + "\n")
print("\n".join(write_checksums(out)))
