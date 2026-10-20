"""API smoke test: chat round-trip on the `chat`/`query` path (no workflow workers needed), meta, knowledge,
memory, SSE replay. Skipped when the local LLM server is not running."""
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from regtest_agent.config import get_settings


def _llm_up() -> bool:
    try:
        return httpx.get(get_settings().llm_base_url.removesuffix("/v1") + "/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _llm_up(), reason="local LLM server not running")


@pytest.fixture(scope="module")
def client(monkeypatch_module=None):
    import regtest_agent.service as service
    orig = service.Service.__init__

    def init(self, settings=None, warm=True):  # no worker warm-up in tests
        orig(self, settings, warm=False)
    service.Service.__init__ = init
    from regtest_agent.api.app import app
    with TestClient(app) as c:
        yield c
    service.Service.__init__ = orig


def test_meta_and_knowledge(client):
    m = client.get("/api/meta").json()
    assert {"understand", "plan", "execute", "verify", "review"} <= {n["id"] for n in m["graph"]["nodes"]}
    assert len(m["tools"]) >= 30 and "llm4fin" in m["sops"]
    ks = {k["domain"]: k for k in client.get("/api/knowledge").json()}
    assert {"finance", "traffic", "power"} <= set(ks) and ks["finance"]["constraints"] == 5
    assert client.get("/api/knowledge/power").json()["representation"]["symbols"]["ExpectedResult"]


def test_chat_roundtrip_and_events(client):
    tid = client.post("/api/threads").json()["id"]
    r = client.post(f"/api/threads/{tid}/messages", data={"text": "你能做什么？"})
    assert r.status_code == 200
    for _ in range(120):
        th = client.get(f"/api/threads/{tid}").json()
        if not th["busy"] and th["status"] == "idle" and len(th["messages"]) >= 2:
            break
        time.sleep(1)
    msgs = th["messages"]
    assert msgs[0]["role"] == "user" and msgs[-1]["role"] == "assistant" and msgs[-1]["content"]
    body = client.get(f"/api/threads/{tid}/events?after=0&follow=0").text  # replay-only SSE
    types = [l.split(":", 1)[1].strip() for l in body.split("\n") if l.startswith("event:")]
    assert "message" in types and "phase" in types and "status" in types
    last = int([l for l in body.split("\n") if l.startswith("id:")][-1].split(":")[1])
    assert client.get(f"/api/threads/{tid}/events?after={last}&follow=0").text == ""


def test_prefs_and_upload_validation(client):
    assert client.put("/api/memory/prefs/judge_samples", json={"value": "3"}).json()["judge_samples"] == "3"
    assert "judge_samples" not in client.delete("/api/memory/prefs/judge_samples").json()
    assert client.put("/api/memory/prefs/bogus", json={"value": 1}).status_code == 400
    tid = client.post("/api/threads").json()["id"]
    bad = client.post(f"/api/threads/{tid}/upload", files={"files": ("x.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 400 and "不支持" in json.loads(bad.text)["detail"]

