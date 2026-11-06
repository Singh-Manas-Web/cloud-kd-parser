"""Calls the teacher model (phi3.5 served by Ollama). Standard library only.

Fixed settings for every student: temperature 0 and seed 42. We also ask Ollama for JSON
output mode ("format": "json") and cap the reply at TEACHER_NUM_PREDICT tokens. The reply text
is returned exactly as Ollama generated it; it is never edited.
"""
import json
import os
import time
import urllib.error
import urllib.request

MODEL = os.environ.get("TEACHER_MODEL", "phi3.5")
OPTIONS = {
    "temperature": 0,
    "seed": 42,
    "num_predict": int(os.environ.get("TEACHER_NUM_PREDICT", "96")),
}
FORMAT_JSON = os.environ.get("TEACHER_FORMAT_JSON", "1") == "1"


def load_prompt(path):
    with open(path, encoding="utf-8") as f:
        template = f.read()
    if "{command}" not in template:
        raise ValueError("prompt template must contain the placeholder {command}")
    return template


def build_prompt(template, command):
    return template.replace("{command}", command)


def ask_teacher(ollama_url, template, command, timeout=600, retries=8):
    body = {
        "model": MODEL,
        "prompt": build_prompt(template, command),
        "stream": False,
        "keep_alive": "24h",
        "options": OPTIONS,
    }
    if FORMAT_JSON:
        body["format"] = "json"
    data = json.dumps(body).encode("utf-8")
    url = ollama_url.rstrip("/") + "/api/generate"
    delay = 5
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))["response"]
        except (urllib.error.URLError, TimeoutError, ConnectionError, KeyError) as exc:
            if attempt == retries:
                raise
            print(f"  teacher call failed ({exc}); retry {attempt}/{retries} in {delay}s", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 60)
