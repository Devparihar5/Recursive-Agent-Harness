"""Command line interface for the recursive harness."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.core.models import Task
from app.harness.loader import load_harness
from app.harness.model import harness_sha256
from app.library.store import ImprovementLibrary
from app.orchestration.pipeline import Pipeline, compare_runs
from app.orchestration.stream import run_stream


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
    hash_command = commands.add_parser("harness-hash")
    hash_command.add_argument("--path", type=Path, default=Path("harnesses/base"))
    run = commands.add_parser("run-task")
    run.add_argument("--task", required=True, type=Path)
    run.add_argument("--mode", choices=["parallel", "sequential"], default="parallel")
    run.add_argument("--k", type=int, default=1)
    run.add_argument("--source", action="append", default=[])
    run.add_argument("--domain")
    stream = commands.add_parser("run-stream")
    stream.add_argument("--task", action="append", required=True, type=Path)
    stream.add_argument("--mode", choices=["parallel", "sequential"], default="parallel")
    stream.add_argument("--k", type=int, default=1)
    stream.add_argument("--domain")
    stream.add_argument("--adopt-supported", action="store_true",
                        help="Adopt evidence-backed pending lessons between tasks")
    library = commands.add_parser("library")
    library_commands = library.add_subparsers(dest="library_command", required=True)
    library_list = library_commands.add_parser("list")
    library_list.add_argument("--query", default="")
    library_list.add_argument("--domain", default="")
    library_list.add_argument("--component", default="")
    library_list.add_argument("--include-archived", action="store_true")
    library_commands.add_parser("pending")
    inspect = library_commands.add_parser("inspect")
    inspect.add_argument("entry_id")
    adopt = library_commands.add_parser("adopt")
    adopt.add_argument("entry_id")
    adopt.add_argument("--note", default="")
    library_diff = library_commands.add_parser("diff")
    library_diff.add_argument("entry_id")
    library_diff.add_argument("--base", type=Path, default=Path("harnesses/base"))
    annotate = library_commands.add_parser("annotate")
    annotate.add_argument("entry_id")
    annotate.add_argument("note")
    archive = library_commands.add_parser("archive")
    archive.add_argument("entry_id")
    archive.add_argument("--reason", default="")
    restore = library_commands.add_parser("restore")
    restore.add_argument("entry_id")
    compare = commands.add_parser("compare-runs")
    compare.add_argument("run1")
    compare.add_argument("run2")
    args = parser.parse_args(argv)
    if args.command == "harness-hash":
        print(harness_sha256(load_harness(args.path).files))
        return 0
    if args.command == "run-stream":
        if not 1 <= args.k <= 5:
            parser.error("--k must be between 1 and 5")
        tasks = [_task_from_file(path, [], args.domain) for path in args.task]
        result = asyncio.run(run_stream(Pipeline(), tasks, mode=args.mode, k=args.k,
                                        adopt_supported=args.adopt_supported))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "run-task":
        if not 1 <= args.k <= 5:
            parser.error("--k must be between 1 and 5")
        task = _task_from_file(args.task, args.source, args.domain)
        result = asyncio.run(Pipeline().run(task, mode=args.mode, k=args.k))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "library":
        store = ImprovementLibrary(Path("improvement_library"))
        if args.library_command == "list":
            value = store.search_entries(args.query, args.domain, args.component, args.include_archived)
        elif args.library_command == "pending":
            value = store.list_pending()
        elif args.library_command == "adopt":
            value = store.adopt(args.entry_id, note=args.note)
        elif args.library_command == "diff":
            value = store.diff_from_base(args.entry_id, args.base)
        elif args.library_command == "annotate":
            value = store.annotate(args.entry_id, args.note)
        elif args.library_command == "archive":
            value = store.archive(args.entry_id, args.reason)
        elif args.library_command == "restore":
            value = store.restore(args.entry_id)
        else:
            value = store.inspect(args.entry_id)
        print(json.dumps(value, indent=2, ensure_ascii=False))
        return 0
    print(json.dumps(compare_runs(Path("runs"), args.run1, args.run2), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
