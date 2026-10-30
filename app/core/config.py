"""Environment configuration; no network or filesystem effects at import."""
from pathlib import Path
import os
from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(extra="allow")
    provider: str = "ollama"
    model: str = "qwen3.5:4b"
    base_url: str = "http://localhost:11434"
    api_key: str = ""
    timeout_seconds: float = 300
    max_steps: int = 50
    max_tokens: int = 4096
    embedding_model: str = "nomic-embed-text:latest"
    default_recursion_mode: str = "parallel"
    default_recursion_k: int = 1
    runs_root: Path = Path("runs")
    harnesses_root: Path = Path("harnesses")


def _dotenv(path: Path = Path(".env")) -> dict[str, str]:
    """Read simple KEY=VALUE settings; process environment takes precedence."""
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.isidentifier():
            values[key] = value.strip().strip('"').strip("'")
    return values


def get_settings() -> Settings:
    file_values = _dotenv()

    def setting(name: str, default: str) -> str:
        return os.environ.get(name, file_values.get(name, default))

    return Settings(
        provider=setting("LLM_PROVIDER", "ollama"),
        model=setting("LLM_MODEL", "qwen3.5:4b"),
        base_url=setting("LLM_BASE_URL", "http://localhost:11434"),
        api_key=setting("LLM_API_KEY", ""),
        timeout_seconds=float(setting("LLM_TIMEOUT_SECONDS", "300")),
        max_steps=int(setting("LLM_MAX_STEPS", "50")),
        max_tokens=int(setting("LLM_MAX_TOKENS", "4096")),
        embedding_model=setting("EMBEDDING_MODEL", "nomic-embed-text:latest"),
        default_recursion_mode=setting("DEFAULT_RECURSION_MODE", "parallel"),
        default_recursion_k=int(setting("DEFAULT_RECURSION_K", "1")),
    )
