"""Small HTTP adapters for local Ollama and OpenAI-compatible servers."""
import httpx
from .base import ModelResponse


class OpenAICompatibleProvider:
    def __init__(self, model: str, base_url: str = "https://api.openai.com/v1", api_key: str = "", timeout: float = 120, max_tokens: int = 4096):
        self.model, self.base_url, self.api_key = model, base_url.rstrip("/"), api_key
        self.timeout, self.max_tokens = timeout, max_tokens

    async def generate(self, messages: list[dict], temperature: float = 0, response_format: dict | None = None) -> ModelResponse:
        payload = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": self.max_tokens}
        if response_format is not None:
            payload["response_format"] = response_format
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        return ModelResponse(content=data["choices"][0]["message"]["content"] or "", token_usage=data.get("usage", {}), model=data.get("model", self.model))


class OllamaProvider:
    def __init__(self, model: str, base_url: str = "http://localhost:11434", timeout: float = 120, max_tokens: int = 4096):
        self.model, self.base_url = model, base_url.rstrip("/")
        self.timeout, self.max_tokens = timeout, max_tokens

    async def generate(self, messages: list[dict], temperature: float = 0, response_format: dict | None = None) -> ModelResponse:
        payload = {"model": self.model, "messages": messages, "stream": False, "options": {"temperature": temperature, "num_predict": self.max_tokens}}
        if response_format is not None:
            payload["format"] = response_format.get("json_schema", {}).get("schema", "json")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        return ModelResponse(content=data["message"]["content"], token_usage={"prompt_tokens": data.get("prompt_eval_count", 0), "completion_tokens": data.get("eval_count", 0)}, model=data.get("model", self.model))


def create_provider(config):
    kwargs = dict(model=config.model, base_url=config.base_url, timeout=config.timeout_seconds, max_tokens=config.max_tokens)
    if config.provider == "ollama":
        return OllamaProvider(**kwargs)
    if config.provider in {"openai", "openai-compatible", "openai_compatible"}:
        return OpenAICompatibleProvider(**kwargs, api_key=config.api_key)
    raise ValueError(f"Unsupported provider: {config.provider}")
