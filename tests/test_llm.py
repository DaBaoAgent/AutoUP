import json

import pytest
import requests

from autoup import llm


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_strip_fence_and_json_extraction(monkeypatch):
    assert llm._strip_fence("```json\n{\"a\": 1}\n```") == '{"a": 1}'
    monkeypatch.setattr(llm, "chat", lambda *args, **kwargs: 'prefix {"x": 2} suffix')
    assert llm.chat_json("p") == {"x": 2}


def test_chat_success(monkeypatch):
    settings = {
        "llm.api_key": "k",
        "llm.base_url": "https://example.test/v1",
        "llm.model": "model",
        "llm.temperature": 0.2,
        "llm.max_tokens": 100,
        "llm.max_retries": 1,
    }
    monkeypatch.setattr(llm.config, "get", lambda key, default=None: settings.get(key, default))
    monkeypatch.setattr(
        llm._SESSION,
        "post",
        lambda *args, **kwargs: FakeResponse(
            payload={"choices": [{"message": {"content": "ok"}}]}
        ),
    )
    assert llm.chat("hello") == "ok"


def test_chat_fails_fast_on_client_error(monkeypatch):
    settings = {
        "llm.api_key": "k",
        "llm.base_url": "https://example.test/v1",
        "llm.model": "model",
        "llm.temperature": 0.2,
        "llm.max_tokens": 100,
        "llm.max_retries": 3,
    }
    monkeypatch.setattr(llm.config, "get", lambda key, default=None: settings.get(key, default))
    monkeypatch.setattr(
        llm._SESSION,
        "post",
        lambda *args, **kwargs: FakeResponse(status_code=400, text="bad request"),
    )
    with pytest.raises(RuntimeError, match="HTTP 400"):
        llm.chat("hello")


def test_chat_handles_request_exception(monkeypatch):
    settings = {
        "llm.api_key": "k",
        "llm.base_url": "https://example.test/v1",
        "llm.model": "model",
        "llm.temperature": 0.2,
        "llm.max_tokens": 100,
        "llm.max_retries": 1,
    }
    monkeypatch.setattr(llm.config, "get", lambda key, default=None: settings.get(key, default))

    def boom(*args, **kwargs):
        raise requests.RequestException("network")

    monkeypatch.setattr(llm._SESSION, "post", boom)
    with pytest.raises(RuntimeError, match="network"):
        llm.chat("hello")
