from pathlib import Path
import difflib
from .loader import load_harness
from .model import Harness


def clone_harness(harness: Harness, destination: str | Path) -> Harness:
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    source = load_harness(harness.path)
    destination.mkdir(parents=True)
    for name, content in source.files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return load_harness(destination)


def diff_harnesses(before: Harness, after: Harness) -> str:
    result = []
    for name in sorted(before.files.keys() | after.files.keys()):
        result.extend(difflib.unified_diff(before.files.get(name, "").splitlines(keepends=True), after.files.get(name, "").splitlines(keepends=True), fromfile=f"before/{name}", tofile=f"after/{name}"))
    return "".join(result)


def get_version(path: str | Path) -> str:
    return load_harness(path).version
