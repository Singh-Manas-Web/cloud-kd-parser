import os

import pytest

pytest.importorskip("fastapi")
os.environ["SKIP_MODEL_LOAD"] = "1"
os.environ.setdefault("MODEL_VERSION", "v-test")
os.environ.setdefault("POD_NAME", "pod-test")

import app as service  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

GOOD = '{"intent": "weather_query", "date": null, "time": null, "place": "london"}'


class FakeParser:
    def generate(self, text):
        return GOOD


@pytest.fixture
def client():
    service.STATE.parser, service.STATE.ready = None, False
    return TestClient(service.app)


def test_health_and_readiness(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 503
    service.STATE.parser, service.STATE.ready = FakeParser(), True
    assert client.get("/readyz").status_code == 200


def test_parse_returns_json_and_headers(client, monkeypatch):
    monkeypatch.setenv("FAULT_INJECT", "0")
    service.STATE.parser, service.STATE.ready = FakeParser(), True
    r = client.post("/parse", json={"text": "what is the weather in london"})
    assert r.status_code == 200
    assert r.json() == {"intent": "weather_query", "date": None, "time": None, "place": "london"}
    assert r.headers["X-Model-Version"] == service.MODEL_VERSION
    assert r.headers["X-Served-By"] == service.SERVED_BY


def test_fault_injection_returns_500(client, monkeypatch):
    monkeypatch.setenv("FAULT_INJECT", "1")
    service.STATE.parser, service.STATE.ready = FakeParser(), True
    r = client.post("/parse", json={"text": "what is the weather in london"})
    assert r.status_code == 500
    assert r.json() == {"error": "invalid_model_output"}
