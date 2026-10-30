from typing import Any, Protocol
from pydantic import BaseModel, Field


class ModelResponse(BaseModel):
    content: str
    token_usage: dict[str, Any] = Field(default_factory=dict)
    model: str = ""


class ModelProvider(Protocol):
    async def generate(self, messages: list[dict], temperature: float = 0, response_format: dict | None = None) -> ModelResponse: ...
