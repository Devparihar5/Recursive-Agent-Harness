"""Command line interface for the recursive harness."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.core.models import Task
from app.library.store import ImprovementLibrary
from app.orchestration.pipeline import Pipeline


def _task_from_file(path: Path, sources: list[str], domain: str | None) -> Task:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    source_paths = [Path(source) for source in sources]
    if not source_paths:
        adjacent = path.with_name(path.stem + "_sources")
        if adjacent.is_dir():
            source_paths = sorted(file for file in adjacent.rglob("*") if file.is_file())
    root = Path.cwd().resolve()
    relative_sources = []
    for source in source_paths:
        resolved = source.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"Source is outside the working directory: {source}")
        relative_sources.append(resolved.relative_to(root).as_posix())
    inferred_domain = domain or ("customer_support" if "customer" in path.stem else "general")
    return Task(task_id=path.stem, description=text, domain=inferred_domain,
                source_files=relative_sources, metadata={"task_file": str(path)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run-task")
    run.add_argument("--task", required=True, type=Path)
    run.add_argument("--mode", choices=["parallel", "sequential"], default="parallel")
    run.add_argument("--k", type=int, default=1)
    run.add_argument("--source", action="append", default=[])
    run.add_argument("--domain")
    library = commands.add_parser("library")
    library_commands = library.add_subparsers(dest="library_command", required=True)
    library_commands.add_parser("list")
    inspect = library_commands.add_parser("inspect")
    inspect.add_argument("entry_id")
    compare = commands.add_parser("compare-runs")
    compare.add_argument("run1")
    compare.add_argument("run2")
    args = parser.parse_args(argv)
    if args.command == "run-task":
        if not 1 <= args.k <= 5:
            parser.error("--k must be between 1 and 5")
        task = _task_from_file(args.task, args.source, args.domain)
        result = asyncio.run(Pipeline().run(task, mode=args.mode, k=args.k))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "library":
        store = ImprovementLibrary(Path("improvement_library"))
        value = store.list_entries() if args.library_command == "list" else store.inspect(args.entry_id)
        print(json.dumps(value, indent=2, ensure_ascii=False))
        return 0
    from app.orchestration.pipeline import compare_runs
    print(json.dumps(compare_runs(Path("runs"), args.run1, args.run2), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
