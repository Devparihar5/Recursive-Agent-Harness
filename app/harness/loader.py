"""Markdown harnesses are data, never executable Python."""
from pathlib import Path
import hashlib
import ast
import re
from .model import Harness

MAX_FILE_BYTES = 128 * 1024
MAX_HARNESS_BYTES = 1024 * 1024
REQUIRED_FILES = {"systemprompt.md", "guardrails.md", "LongTermMEMORY.md", "tool_guidance.md"}


def safe_path(root: Path, relative: str) -> Path:
    root = Path(root).resolve()
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or ":" in relative or "\\" in relative:
        raise ValueError(f"Unsafe harness path: {relative}")
    result = (root / rel).resolve()
    if not result.is_relative_to(root):
        raise ValueError(f"Harness path escapes root: {relative}")
    return result


def load_harness(path: str | Path) -> Harness:
    root = Path(path).resolve()
    if not root.is_dir():
        raise ValueError(f"Harness directory does not exist: {root}")
    files = {}
    total = 0
    for file in sorted(root.rglob("*")):
        if file.is_symlink() or (hasattr(file, "is_junction") and file.is_junction()):
            raise ValueError(f"Links are forbidden in harnesses: {file.name}")
        if file.is_file():
            name = file.relative_to(root).as_posix()
            if file.suffix.lower() not in {".md", ".py"}:
                raise ValueError(f"Harness files must be Markdown or inert Python: {name}")
            if file.suffix.lower() == ".py" and name.split("/")[0] not in {"scripts", "plugins"}:
                raise ValueError(f"Python artifacts must be under scripts/ or plugins/: {name}")
            size = file.stat().st_size
            total += size
            if size > MAX_FILE_BYTES or total > MAX_HARNESS_BYTES:
                raise ValueError("Harness exceeds size limit")
            text = file.read_text(encoding="utf-8")
            if "\x00" in text:
                raise ValueError(f"NUL byte in harness file: {name}")
            if file.suffix.lower() == ".py":
                try:
                    tree = ast.parse(text, filename=name)
                except SyntaxError as exc:
                    raise ValueError(f"Invalid Python syntax in {name}: {exc.msg}") from exc
                if name.startswith("plugins/"):
                    hooks = {node.name for node in ast.walk(tree)
                             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
                    if not hooks.intersection({"before_model_call", "after_model_call",
                                               "before_tool_call", "after_tool_call",
                                               "before_task_complete"}):
                        raise ValueError(f"Plugin has no recognized hook: {name}")
            files[name] = text
    if not files or not any(text.strip() for text in files.values()):
        raise ValueError("Harness must contain nonempty Markdown instructions")
    missing = REQUIRED_FILES - files.keys()
    if missing:
        raise ValueError(f"Harness missing required files: {', '.join(sorted(missing))}")
    for name in REQUIRED_FILES:
        if not files[name].strip():
            raise ValueError(f"Required harness file is empty: {name}")
    for name, content in files.items():
        if name.startswith("skills/") and name.endswith("/SKILL.md"):
            if not re.search(r"(?im)^\s*(triggers?|activation):\s*\S+", content):
                raise ValueError(f"Skill requires a trigger or activation description: {name}")
        if name.endswith(".md"):
            for reference in re.findall(r"(?<![\w/])(?:scripts/[^\s`'\"<>]+\.py|sub_agents/[^\s`'\"<>]+/AGENT\.md)", content):
                if reference not in files:
                    raise ValueError(f"Referenced harness artifact is missing: {reference}")
    digest = hashlib.sha256()
    for name, text in sorted(files.items()):
        digest.update(name.encode() + b"\x00" + text.encode() + b"\x00")
    return Harness(path=root, version=digest.hexdigest()[:16], files=files)
