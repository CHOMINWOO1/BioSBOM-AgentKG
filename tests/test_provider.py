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


def test_responses_transport_strict_schema_and_nonstored_request(endpoint):
    url, state = endpoint
    state["body"] = {
        "status": "completed",
        "output": [
            {"type": "reasoning"},
            {"type": "message", "content": [{"type": "output_text", "text": '{"ok":true}'}]},
        ],
        "usage": {"total_tokens": 51},
    }
    reply = ChatProvider(url, "fixture", api_style="responses").complete(
        "context", {}, {"type": "object"}, max_tokens=300, timeout=2
    )
    assert reply.payload == {"ok": True} and reply.total_tokens == 51
    assert state["path"] == "/v1/responses"
    assert state["request"]["max_output_tokens"] == 300
    assert state["request"]["store"] is False
    assert state["request"]["text"]["format"]["strict"] is True
    assert "temperature" not in state["request"]


@pytest.mark.parametrize(
    "body,code",
    [
        ({"status": "incomplete", "output": []}, "incomplete_response"),
        (
            {
                "status": "completed",
                "output": [
                    {"type": "message", "content": [{"type": "refusal", "refusal": "PRIVATE"}]}
                ],
            },
            "invalid_response",
        ),
        ({"status": "completed", "output": []}, "invalid_response"),
    ],
)
def test_responses_failed_output_preserves_known_usage(endpoint, body, code):
    url, state = endpoint
    body["usage"] = {"total_tokens": 123}
    state["body"] = body
    with pytest.raises(ProviderError) as error:
        ChatProvider(url, "fixture", api_style="responses").complete(
            "context", {}, {}, max_tokens=300, timeout=2
        )
    assert str(error.value) == code and error.value.total_tokens == 123


def test_failed_call_usage_is_not_reported_as_zero_or_complete(case):
    from biosbom_agentkg.multiagent.engine import run_case
    from biosbom_agentkg.multiagent.models import RunConfig

    class Failed:
        models = {"context": "fake-test"}

        def complete(self, *args, **kwargs):
            raise ProviderError("incomplete_response", 77)

    result = run_case(case, RunConfig(mode="llm", max_revisions=0), Failed())
    assert result.calls == 1 and result.reported_total_tokens == 77
    assert result.usage_complete and result.status == "blocked"

    class Unknown(Failed):
        def complete(self, *args, **kwargs):
            raise ProviderError("connection_failed")

    result = run_case(case, RunConfig(mode="llm", max_revisions=0), Unknown())
    assert not result.usage_complete
