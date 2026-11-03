"""Embedding client for nomic-embed-text (or any Ollama embedding model).

Provides both an async path (embed_async) and a synchronous wrapper (embed)
that runs the coroutine in a new event loop so it can be called from
non-async contexts such as LibraryIndex.add().

Errors are always caught and logged; callers receive an empty list [] as the
fallback so keyword ranking takes over gracefully.
"""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

_DIM = 768  # nomic-embed-text fixed output dimension


class EmbeddingClient:
    """Thin async wrapper around Ollama /api/embeddings."""

    def __init__(
        self,
        model: str = "nomic-embed-text:latest",
        base_url: str = "http://localhost:11434",
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def embed_async(self, text: str) -> list[float]:
        """Return a 768-dim float vector, or [] on any error."""
        if not text or not text.strip():
            return []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text[:8192]},
                )
                response.raise_for_status()
                vector = response.json().get("embedding", [])
                if not isinstance(vector, list) or len(vector) != _DIM:
                    log.warning(
                        "Unexpected embedding dimension %d from %s",
                        len(vector),
                        self.model,
                    )
                    return []
                return [float(v) for v in vector]
        except Exception as exc:
            log.warning("Embedding failed (%s: %s) — falling back to keyword ranking", type(exc).__name__, exc)
            return []

    def embed(self, text: str) -> list[float]:
        """Synchronous wrapper — runs embed_async in a fresh event loop."""
        if not text or not text.strip():
            return []
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text[:8192]},
                )
                response.raise_for_status()
                vector = response.json().get("embedding", [])
                if not isinstance(vector, list) or len(vector) != _DIM:
                    return []
                return [float(v) for v in vector]
        except Exception as exc:
            log.warning("Sync embedding wrapper failed: %s", exc)
            return []

    @staticmethod
    def entry_text(metadata: dict) -> str:
        """Produce the text that represents a library entry for embedding."""
        parts: list[str] = []
        exp = metadata.get("experience", {})
        if isinstance(exp, dict):
            for key in ("cue", "lesson", "evidence"):
                val = exp.get(key, "")
                if isinstance(val, str) and val.strip():
                    parts.append(val.strip())
                elif isinstance(val, list):
                    parts.extend(str(v) for v in val if v)
        parts.append(str(metadata.get("domain", "")))
        parts.append(str(metadata.get("task_shape", "")))
        components = metadata.get("components", [])
        if isinstance(components, list):
            parts.extend(str(c) for c in components)
        return " ".join(p for p in parts if p).strip()

    @staticmethod
    def task_text(task) -> str:
        """Produce the query text from a Task object for retrieval."""
        if hasattr(task, "model_dump"):
            data = task.model_dump()
        elif hasattr(task, "__dict__"):
            data = vars(task)
        else:
            data = dict(task) if isinstance(task, dict) else {}
        parts: list[str] = []
        for key in ("description", "prompt", "input", "domain"):
            val = data.get(key, "")
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
        metadata = data.get("metadata", {})
        if isinstance(metadata, dict):
            shape = metadata.get("task_shape", "")
            if shape:
                parts.append(str(shape))
        return " ".join(parts).strip()
