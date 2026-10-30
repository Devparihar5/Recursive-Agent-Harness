from pathlib import Path
from .loader import load_harness


def validate_harness(path: str | Path) -> list[str]:
    try:
        load_harness(path)
        return []
    except (ValueError, OSError, UnicodeError) as exc:
        return [str(exc)]
