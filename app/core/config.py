"""Environment configuration; no network or filesystem effects at import."""
from pathlib import Path
import os
from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(extra="allow")
    provider: str = "ollama"
    model: str = "qwen3.5:4b"
    base_url: str = "http://localhost:11434"
    api_key: str = ""
    timeout_seconds: float = 300
    max_steps: int = 50
    max_tokens: int = 4096
    max_execution_seconds: float = 3600
    max_execution_tokens: int = 100000
    allow_unsafe_harness_code: bool = False
    trusted_harness_sha256: list[str] = Field(default_factory=list)
    embedding_model: str = "nomic-embed-text:latest"
    verifier_model: str = ""
    default_recursion_mode: str = "parallel"
    default_recursion_k: int = 1
    runs_root: Path = Path("runs")
    benchmark_results_root: Path = Path("benchmark_results")
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
        max_execution_seconds=float(setting("MAX_EXECUTION_SECONDS", "3600")),
        max_execution_tokens=int(setting("MAX_EXECUTION_TOKENS", "100000")),
        allow_unsafe_harness_code=setting("ALLOW_UNSAFE_HARNESS_CODE", "false").lower() in {"1", "true", "yes", "on"},
        trusted_harness_sha256=[value.strip().lower() for value in setting("TRUSTED_HARNESS_SHA256", "").split(",") if value.strip()],
        embedding_model=setting("EMBEDDING_MODEL", "nomic-embed-text:latest"),
        verifier_model=setting("VERIFIER_MODEL", ""),
        default_recursion_mode=setting("DEFAULT_RECURSION_MODE", "parallel"),
        default_recursion_k=int(setting("DEFAULT_RECURSION_K", "1")),
        benchmark_results_root=Path(setting("BENCHMARK_RESULTS_ROOT", "benchmark_results")),
    )
