from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app import store
import server


@pytest.fixture
def track(monkeypatch):
    store.disable_persist()
    store.reset()
    spy = Mock()
    monkeypatch.setattr(server, "track", spy)
    monkeypatch.setattr(server, "get_flag", lambda *args, **kwargs: True)
    # Keep temporary failure routes local to each test.
    monkeypatch.setattr(server.app.router, "routes", list(server.app.router.routes))
    return spy


@pytest.mark.parametrize("context_key", ["chat-user", None])
def test_chat_agent_error_tracked_once(monkeypatch, track, context_key):
    async def fail(*args, **kwargs):
        raise RuntimeError("agent failed")

    monkeypatch.setattr(server, "run_agent_async", fail)
    response = TestClient(server.app).post(
        "/api/chat", json={"message": "Help with my room", "context_key": context_key},
    )

    assert response.status_code == 500
    track.assert_called_once()
    event, key, data = track.call_args.args
    assert event == "decora_request_error"
    if context_key:
        assert key == context_key
    else:
        assert key.startswith("anon-")
    assert data == {"route": "/api/chat", "status": 500, "error": "RuntimeError"}
    assert track.call_args.kwargs == {}


def test_chat_success_not_tracked(monkeypatch, track):
    async def succeed(*args, **kwargs):
        return {"response": "Hello", "metadata": {}}

    monkeypatch.setattr(server, "run_agent_async", succeed)
    response = TestClient(server.app).post(
        "/api/chat", json={"message": "Hello", "context_key": "chat-user"},
    )
    assert response.status_code == 200
    track.assert_not_called()


def test_bad_request_not_tracked(track):
    response = TestClient(server.app).post(
        "/api/rooms/rename", json={"name": "   ", "context_key": "test-user"},
    )
    assert response.status_code == 400
    track.assert_not_called()


@pytest.mark.parametrize("status", [400, 403, 422])
def test_chat_http_client_error_not_tracked(monkeypatch, track, status):
    def fail(*args, **kwargs):
        raise HTTPException(status_code=status)

    monkeypatch.setattr(server, "build_context", fail)
    response = TestClient(server.app).post(
        "/api/chat", json={"message": "Hello", "context_key": "chat-user"},
    )
    assert response.status_code == status
    track.assert_not_called()


@pytest.mark.parametrize("source", ["query", "body", "missing"])
@pytest.mark.parametrize("failure", ["response", "exception", "http_exception"])
def test_middleware_errors(track, source, failure):
    path = "/api/test-error"

    async def fail():
        if failure == "exception":
            raise ValueError("unhandled")
        if failure == "http_exception":
            raise HTTPException(status_code=503)
        return JSONResponse(status_code=503, content={"detail": "unavailable"})

    server.app.add_api_route(path, fail, methods=["POST"])

    payload = {"message": "Hello"}
    params = {}
    if source == "query":
        params["context_key"] = "test-user"
    elif source == "body":
        payload["context_key"] = "test-user"
    response = TestClient(server.app, raise_server_exceptions=False).post(
        path, params=params, json=payload,
    )
    status = 500 if failure == "exception" else 503
    assert response.status_code == status
    if source == "missing":
        track.assert_not_called()
    else:
        track.assert_called_once_with(
            "decora_request_error", "test-user",
            {
                "route": path,
                "status": status,
                "error": "ValueError" if failure == "exception" else "HTTPException",
            },
        )


def test_chat_failure_outside_agent_guard_tracked(monkeypatch, track):
    def fail(*args):
        raise ValueError("context failed")

    monkeypatch.setattr(server, "build_context", fail)
    response = TestClient(server.app, raise_server_exceptions=False).post(
        "/api/chat", json={"message": "Hello", "context_key": "chat-user"},
    )
    assert response.status_code == 500
    track.assert_called_once_with(
        "decora_request_error", "chat-user",
        {"route": "/api/chat", "status": 500, "error": "ValueError"},
    )


def test_non_api_failure_not_tracked(track):
    async def fail():
        raise RuntimeError("frontend failure")

    server.app.add_api_route("/test-error", fail)
    response = TestClient(server.app, raise_server_exceptions=False).get(
        "/test-error", params={"context_key": "test-user"},
    )
    assert response.status_code == 500
    track.assert_not_called()
