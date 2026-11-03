"""Markdown harnesses are data, never executable Python."""
from pathlib import Path
import ast
import re
from .model import Harness, safe_path, harness_sha256

MAX_FILE_BYTES = 128 * 1024
MAX_HARNESS_BYTES = 1024 * 1024
REQUIRED_FILES = {"systemprompt.md", "guardrails.md", "LongTermMEMORY.md", "tool_guidance.md"}


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
                    if any(isinstance(node, ast.AsyncFunctionDef) and node.name in {
                            "before_model_call", "after_model_call", "before_tool_call",
                            "after_tool_call", "before_task_complete"} for node in tree.body):
                        raise ValueError(f"Plugin hooks must be synchronous functions: {name}")
                    hooks = {node.name for node in tree.body
                             if isinstance(node, ast.FunctionDef)}
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
    return Harness(path=root, version=harness_sha256(files)[:16], files=files)
