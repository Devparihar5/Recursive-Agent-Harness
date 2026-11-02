import asyncio
import json

import httpx
import pytest

from app.llm.base import ModelResponse
from app.llm.providers import OllamaProvider


def _mock_client(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    client_type = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client_type(transport=transport, **kwargs))


def test_ollama_chat_assembles_streamed_content_and_usage(monkeypatch):
    def handler(request):
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert payload["think"] is False
        assert payload["format"] == "json"
        chunks = [
            {"model": "qwen3.5:4b", "message": {"content": '{"action":'}, "done": False},
            {"model": "qwen3.5:4b", "message": {"content": '"final"}'}, "done": False},
            {"model": "qwen3.5:4b", "message": {"content": ""}, "done": True,
             "prompt_eval_count": 12, "eval_count": 4},
        ]
        return httpx.Response(200, text="\n".join(json.dumps(item) for item in chunks) + "\n")

    _mock_client(monkeypatch, handler)
    result = asyncio.run(OllamaProvider("qwen3.5:4b").generate(
        [{"role": "user", "content": "Return JSON"}], response_format={"type": "json_object"}))
    assert result == ModelResponse(content='{"action":"final"}',
                                   token_usage={"prompt_tokens": 12, "completion_tokens": 4},
                                   model="qwen3.5:4b")


def test_ollama_timeout_explains_model_and_limit(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("", request=request)

    _mock_client(monkeypatch, handler)
    with pytest.raises(TimeoutError, match="qwen3.5:4b.*30 seconds"):
        asyncio.run(OllamaProvider("qwen3.5:4b", timeout=30).generate(
            [{"role": "user", "content": "Hello"}]))


def test_ollama_rejects_incomplete_stream(monkeypatch):
    _mock_client(monkeypatch, lambda request: httpx.Response(200, text=json.dumps({
        "message": {"content": "partial"}, "done": False
    }) + "\n"))
    with pytest.raises(ValueError, match="before completion"):
        asyncio.run(OllamaProvider("qwen3.5:4b").generate(
            [{"role": "user", "content": "Hello"}]))
