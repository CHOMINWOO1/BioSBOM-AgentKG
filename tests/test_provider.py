import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from biosbom_agentkg.multiagent.provider import ChatProvider, ProviderError


@pytest.fixture
def endpoint():
    state = {
        "code": 200,
        "body": {
            "choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}],
            "usage": {"total_tokens": 42},
        },
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            state["request"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["authorization"] = self.headers.get("Authorization")
            state["path"] = self.path
            self.send_response(state["code"])
            if state["code"] == 302:
                self.send_header("Location", "https://example.invalid/credential-sink")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(state["body"]).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1", state
    server.shutdown()
    server.server_close()
    thread.join()


def test_transport_body_and_usage(endpoint):
    url, state = endpoint
    provider = ChatProvider(url, "local-fixture", role_models={"triage": "triage-fixture"})
    result = provider.complete("triage", {"data": 1}, {"type": "object"}, max_tokens=256, timeout=2)
    assert result.payload == {"ok": True}
    assert result.total_tokens == 42
    assert state["path"] == "/v1/chat/completions"
    assert state["request"]["model"] == "triage-fixture"
    assert state["request"]["max_tokens"] == 256
    assert state["request"]["response_format"] == {"type": "json_object"}
    assert state["authorization"] is None


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"code": 401, "body": {"private": "DO_NOT_LOG"}}, "http_401"),
        ({"code": 302}, "redirect_refused"),
        ({"body": {"choices": []}}, "invalid_response"),
        (
            {"body": {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}},
            "incomplete_response",
        ),
        (
            {"body": {"choices": [{"finish_reason": "stop", "message": {"content": "NOT JSON"}}]}},
            "invalid_response",
        ),
        (
            {"body": {"choices": [{"finish_reason": "stop", "message": {"content": "[]"}}]}},
            "invalid_response",
        ),
        (
            {
                "body": {
                    "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
                    "usage": {"total_tokens": -1},
                }
            },
            "invalid_usage",
        ),
    ],
)
def test_transport_fails_closed_without_response_details(endpoint, change, expected):
    url, state = endpoint
    state.update(change)
    with pytest.raises(ProviderError) as error:
        ChatProvider(url, "fixture").complete("context", {}, {}, max_tokens=256, timeout=2)
    assert str(error.value) == expected
    assert "DO_NOT_LOG" not in str(error.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://external.example/v1",
        "https://user:password@example.test/v1",
        "https://example.test/v1?api_key=bad",
        "file:///private",
        "https://example.test/v1#secret",
    ],
)
def test_unsafe_endpoint_configuration_is_rejected(url):
    with pytest.raises(ValueError):
        ChatProvider(url, "fixture")


def test_blank_model_requires_explicit_selection():
    with pytest.raises(ValueError):
        ChatProvider("http://localhost:11434/v1", "")
