"""The real provider adapter, exercised against a local fake Messages endpoint (no network, no key)."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.llm import AnthropicProvider, LLMError
from app.settings import Settings

REQUESTS: list[dict] = []


class FakeMessages(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep test output clean
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        REQUESTS.append({"path": self.path, "body": body})
        user = body["messages"][0]["content"]
        if "SLOW" in user:
            time.sleep(1.5)
        stop_reason = "max_tokens" if "TRUNCATE" in user else "end_turn"
        if "NOUSAGE" in user:
            payload = {
                "id": "msg_2",
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 2},
            }
        else:
            payload = {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "content": [{"type": "text", "text": "STATUS: ANSWERED\nANSWER: hi [NS-TRV-2026#3]"}],
                "stop_reason": stop_reason,
                "stop_sequence": None,
                "usage": {"input_tokens": 1200, "output_tokens": 150},
            }
        data = json.dumps(payload).encode()
        try:
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass


@pytest.fixture
def fake_api(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeMessages)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    REQUESTS.clear()
    yield
    server.shutdown()


def test_provider_records_usage_and_sends_config(fake_api):
    p = AnthropicProvider(Settings(model="claude-opus-5-5", effort="low", timeout_s=5, max_retries=0))
    r = p.generate("sys", "question", max_tokens=500)
    assert r.text.startswith("STATUS: ANSWERED")
    assert (r.input_tokens, r.output_tokens) == (1200, 150)
    assert r.latency_ms is not None
    body = REQUESTS[0]["body"]
    assert body["model"] == "claude-opus-5-5" and body["system"] == "sys" and body["max_tokens"] == 500
    assert body["output_config"] == {"effort": "low"}


def test_effort_omitted_when_unset(fake_api):
    AnthropicProvider(Settings(effort=None, timeout_s=5, max_retries=0)).generate("s", "NOUSAGE", max_tokens=10)
    assert "output_config" not in REQUESTS[0]["body"]


def test_provider_timeout_becomes_llm_error(fake_api):
    p = AnthropicProvider(Settings(timeout_s=0.3, max_retries=0))
    with pytest.raises(LLMError) as e:
        p.generate("sys", "SLOW question", max_tokens=10)
    assert e.value.kind == "timeout" and e.value.latency_ms is not None
    assert "sk-test" not in str(e.value)


def test_truncated_output_becomes_llm_error(fake_api):
    p = AnthropicProvider(Settings(timeout_s=5, max_retries=0))
    with pytest.raises(LLMError) as e:
        p.generate("sys", "TRUNCATE question", max_tokens=10)
    assert e.value.kind == "truncated" and e.value.latency_ms is not None


def test_truncated_output_error_keeps_token_usage(fake_api):
    p = AnthropicProvider(Settings(timeout_s=5, max_retries=0))
    with pytest.raises(LLMError) as e:
        p.generate("sys", "TRUNCATE question", max_tokens=10)
    assert (e.value.input_tokens, e.value.output_tokens) == (1200, 150)


def test_truncated_approach_response_records_tokens_and_cost(fake_api, make_approaches):
    p = AnthropicProvider(Settings(model="claude-opus-5-5", timeout_s=5, max_retries=0))
    resp = make_approaches(p)["basic_rag"].run("TRUNCATE Who approves travel over $2,000?", "employee")
    assert resp.status == "error" and resp.error.startswith("truncated")
    assert (resp.input_tokens, resp.output_tokens) == (1200, 150)
    assert resp.estimated_cost_usd is not None and resp.estimated_cost_usd > 0
