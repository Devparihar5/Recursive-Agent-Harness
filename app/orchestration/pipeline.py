"""Connect task-level recursion with selective cross-task experience retention."""
from __future__ import annotations

import json
import re
import inspect
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.models import ExecutionRecord, ImprovementStep
from app.executor.executor import AgentExecutor
from app.harness.loader import load_harness
from app.improvement.recursion import ImprovementEngine
from app.improvement.reflector import Reflector
from app.improvement.selector import BlindSelector
from app.improvement.probe import BehavioralAnalyzer
from app.library.embeddings import EmbeddingClient
from app.library.store import ImprovementLibrary
from app.llm.providers import create_provider


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", value).strip("._")
    if not safe:
        raise ValueError("Task identifier must contain a letter or number")
    return safe[:100]


async def _emit(callback, event_type: str, **fields) -> None:
    if callback is None:
        return
    result = callback({"type": event_type, **fields})
    if inspect.isawaitable(result):
        await result


def _write_checkpoint(task_root: Path, data: dict) -> None:
    """Atomically write a partial or complete pipeline result for resume support."""
    tmp = task_root / "pipeline.json.tmp"
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(task_root / "pipeline.json")


def _load_checkpoint(task_root: Path) -> dict | None:
    """Return a previously written pipeline checkpoint, or None if none exists."""
    path = task_root / "pipeline.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


class Pipeline:
    def __init__(self, config: Settings | None = None, provider=None,
                 library_root: Path | str = "improvement_library",
                 workspace_root: Path | str = "runs",
                 embedder=None):
        self.config = config or get_settings()
        self.provider = provider or create_provider(self.config)
        self.embedder = embedder or self._create_embedder()
        self.library = ImprovementLibrary(Path(library_root), embedder=self.embedder)
        self.workspace_root = Path(workspace_root)

    def _create_embedder(self):
        """Create an EmbeddingClient from config."""
        model = getattr(self.config, "embedding_model", "nomic-embed-text:latest")
        base_url = getattr(self.config, "base_url", "http://localhost:11434")
        return EmbeddingClient(model=model, base_url=base_url)


    async def run_base(self, task, *, event_callback=None, resume: bool = False) -> dict:
        """Execute once with the common harness and skip improvement stages.

        If *resume* is True and a completed checkpoint already exists for this
        task, the existing result is returned immediately without re-running.
        """
        task_id = _safe_id(task.task_id or task.id)
        task.task_id = task_id
        task_root = self.workspace_root / task_id
        task_root.mkdir(parents=True, exist_ok=True)
        (task_root / "task.json").write_text(task.model_dump_json(indent=2), encoding="utf-8")

        # Resume: if a complete base result exists, re-use it.
        if resume:
            checkpoint = _load_checkpoint(task_root)
            if (checkpoint and checkpoint.get("mode") == "base"
                    and checkpoint.get("selected_execution_id")
                    and checkpoint.get("deliverable")):
                await _emit(event_callback, "task.started", task_id=task_id,
                            mode="base", k=0, resumed=True)
                await _emit(event_callback, "stage", stage="BASE EXECUTION (resumed from checkpoint)")
                await _emit(event_callback, "task.completed", task_id=task_id,
                            execution_id=checkpoint["selected_execution_id"])
                return checkpoint

        await _emit(event_callback, "task.started", task_id=task_id, mode="base", k=0)
        harness = load_harness(Path(self.config.harnesses_root) / "base")
        record = await AgentExecutor(self.provider, task_root, self.config,
                                     event_callback=event_callback).execute(task, harness)
        result = {"task_id": task_id, "mode": "base", "k": 0,
                  "base_harness_version": harness.version,
                  "selected_harness_version": harness.version,
                  "selected_execution_id": record.execution_id,
                  "deliverable": record.deliverable, "steps": [],
                  "retrieved_experiences": [], "reflection": None,
                  "library_entry": None,
                  "metrics": {"executions": 1, "tool_calls": len(record.tool_calls),
                              "latency_seconds": record.latency,
                              "model_tokens": record.token_usage,
                              "execution_failures": int(record.status != "completed")},
                  "stages": ["TASK RECEIVED", "BASE EXECUTION"],
                  "_checkpoint_stage": "base_done"}
        _write_checkpoint(task_root, result)
        await _emit(event_callback, "task.completed" if record.status == "completed" else "task.failed",
                    task_id=task_id, execution_id=record.execution_id, error=record.error)
        return result

    async def run(self, task, *, mode: str = "parallel", k: int = 1,
                  event_callback=None, resume: bool = False) -> dict:
        if mode not in {"parallel", "sequential"} or not 1 <= k <= 5:
            raise ValueError("mode must be parallel or sequential, with k from 1 to 5")
        task_id = _safe_id(task.task_id or task.id)
        task.task_id = task_id
        forbidden = ("answer", "ground_truth", "score", "grader", "rubric", "benchmark")
        task.metadata = {key: value for key, value in task.metadata.items()
                         if not any(word in key.casefold() for word in forbidden)}
        task_root = self.workspace_root / task_id
        task_root.mkdir(parents=True, exist_ok=True)
        (task_root / "task.json").write_text(task.model_dump_json(indent=2), encoding="utf-8")

        # --- Determine whether we can resume from a checkpoint ---
        checkpoint = _load_checkpoint(task_root) if resume else None
        checkpoint_stage = (checkpoint or {}).get("_checkpoint_stage", "")

        await _emit(event_callback, "task.started", task_id=task_id, mode=mode, k=k,
                    resumed=bool(checkpoint_stage))

        base = load_harness(Path(self.config.harnesses_root) / "base")
        experiences = self.library.retrieve(task, limit=3)
        executor = AgentExecutor(self.provider, task_root, self.config,
                                 event_callback=event_callback)
        engine = ImprovementEngine(self.provider, executor, task_root / "candidates",
                                   event_callback=event_callback)

        # --- BASE EXECUTION (skip if checkpoint has it) ---
        if checkpoint_stage in ("base_done", "steps_done", "selection_done", "reflection_done"):
            # Reload base execution record from disk via the checkpoint's execution id.
            await _emit(event_callback, "stage",
                        stage="BASE EXECUTION (resumed from checkpoint)")
        else:
            # Run base fresh and checkpoint immediately so a later failure can skip it.
            base_exec_result = await self.run_base(task, event_callback=event_callback)
            # Save partial checkpoint so resume can skip base next time.
            _write_checkpoint(task_root, {
                "task_id": task_id, "mode": mode, "k": k,
                "base_harness_version": base.version,
                "selected_execution_id": base_exec_result.get("selected_execution_id"),
                "deliverable": base_exec_result.get("deliverable", ""),
                "steps": [], "retrieved_experiences": [],
                "reflection": None, "library_entry": None,
                "_checkpoint_stage": "base_done",
            })
            checkpoint_stage = "base_done"

        # --- IMPROVEMENT STEPS ---
        if checkpoint_stage in ("steps_done", "selection_done", "reflection_done"):
            # Reload completed steps from the checkpoint.
            raw_steps = (checkpoint or {}).get("steps", [])
            steps = [ImprovementStep.model_validate(s) for s in raw_steps]
            await _emit(event_callback, "stage",
                        stage=f"IMPROVEMENT STEPS (resumed {len(steps)} steps from checkpoint)")
        else:
            if mode == "parallel":
                steps = await engine.parallel_round(task, base, experiences, k)
            else:
                steps = []
                current = base
                for round_index in range(k):
                    round_steps = await engine.single_round(task, current,
                        history=[step.model_dump(mode="json") for step in steps],
                        experiences=experiences)
                    step = round_steps[0]
                    steps.append(step)
                    current = load_harness(step.successor_harness or current.path)
                    # Checkpoint after each sequential step so partial progress is saved.
                    _write_checkpoint(task_root, {
                        "task_id": task_id, "mode": mode, "k": k,
                        "base_harness_version": base.version,
                        "steps": [s.model_dump(mode="json") for s in steps],
                        "retrieved_experiences": [e["id"] for e in experiences],
                        "reflection": None, "library_entry": None,
                        "_checkpoint_stage": f"step_{round_index}_done",
                        "_steps_completed": round_index + 1,
                    })

            # Full steps checkpoint (parallel or after all sequential rounds).
            _write_checkpoint(task_root, {
                "task_id": task_id, "mode": mode, "k": k,
                "base_harness_version": base.version,
                "steps": [step.model_dump(mode="json") for step in steps],
                "retrieved_experiences": [e["id"] for e in experiences],
                "reflection": None, "library_entry": None,
                "_checkpoint_stage": "steps_done",
            })
            checkpoint_stage = "steps_done"

        # --- SELECTION ---
        baseline_probe = steps[0].probe_results[0]
        all_probes = [probe for step in steps for probe in step.probe_results]
        terminal_probes = []
        seen_executions: set[str] = set()
        for probe in all_probes:
            if (probe.execution is not None and probe.execution.execution_id not in seen_executions
                    and probe.execution.deliverable.strip()):
                terminal_probes.append(probe)
                seen_executions.add(probe.execution.execution_id)

        if checkpoint_stage in ("selection_done", "reflection_done"):
            selected_execution_id = (checkpoint or {}).get("selected_execution_id")
            await _emit(event_callback, "selection.started", task_id=task_id)
            await _emit(event_callback, "selection.completed", task_id=task_id,
                        execution_id=selected_execution_id, resumed=True)
        else:
            await _emit(event_callback, "selection.started", task_id=task_id)
            selected_execution_id = (
                await BlindSelector(self.provider,
                    source_root=getattr(self.config, "source_root", Path.cwd())
                ).select(task, terminal_probes)
                if len(terminal_probes) > 1
                else (terminal_probes[0].execution.execution_id if terminal_probes
                      else baseline_probe.execution.execution_id)
            )
            await _emit(event_callback, "selection.completed", task_id=task_id,
                        execution_id=selected_execution_id)

        all_candidates = {probe.candidate.id: probe.candidate for probe in all_probes
                          if probe.candidate is not None}
        selected_probe = next((probe for probe in terminal_probes
                               if probe.execution.execution_id == selected_execution_id), baseline_probe)
        selected_candidate = all_candidates.get(selected_probe.candidate_id)
        selected_harness = load_harness(selected_candidate.harness_path if selected_candidate else base.path)

        # Checkpoint after selection.
        _write_checkpoint(task_root, {
            "task_id": task_id, "mode": mode, "k": k,
            "base_harness_version": base.version,
            "selected_execution_id": selected_execution_id,
            "selected_harness_version": selected_harness.version,
            "deliverable": selected_probe.execution.deliverable if selected_probe.execution else "",
            "steps": [step.model_dump(mode="json") for step in steps],
            "retrieved_experiences": [e["id"] for e in experiences],
            "reflection": None, "library_entry": None,
            "_checkpoint_stage": "selection_done",
        })
        checkpoint_stage = "selection_done"

        # --- REFLECTION + LIBRARY ---
        if checkpoint_stage == "reflection_done":
            reflection = (checkpoint or {}).get("reflection")
            library_entry_id = (checkpoint or {}).get("library_entry")
            library_entry = {"id": library_entry_id} if library_entry_id else None
        else:
            reflection = None
            library_entry = None
            try:
                await _emit(event_callback, "reflection.started", task_id=task_id)
                reflection = await Reflector(self.provider).reflect(task,
                    list(all_candidates.values()), all_probes, selected_probe.candidate_id,
                    history=steps, base_harness=base, selected_harness=selected_harness)
                await _emit(event_callback, "reflection.completed", task_id=task_id,
                            lesson=reflection.get("lesson"))
                lesson = reflection.get("lesson")
                helped = [a for a in reflection.get("attributions", []) if a.get("verdict") == "HELPED"]
                if (isinstance(lesson, dict) and lesson.get("cue") and lesson.get("lesson")
                        and lesson.get("evidence") and helped
                        and selected_harness.version != base.version):
                    experience = {**lesson, "origin_task_id": task_id,
                                  "source_candidate": selected_probe.candidate_id,
                                  "source_execution_id": selected_probe.execution.execution_id,
                                  "attributions": reflection.get("attributions", []),
                                  "components": sorted({a.get("component", "") for a in helped})}
                    # Store as pending - user must explicitly adopt via API/UI
                    library_entry = self.library.add_pending(selected_harness, experience,
                        domain=task.domain, task_shape=str(task.metadata.get("task_shape", task.domain)))
                    await _emit(event_callback, "library.pending", task_id=task_id,
                                entry_id=library_entry["id"])
            except Exception as exc:
                reflection = {"error": str(exc), "lesson": "NO_ENTRY"}
                await _emit(event_callback, "reflection.failed", task_id=task_id, error=str(exc))

        result = {"task_id": task_id, "mode": mode, "k": k,
                  "base_harness_version": base.version,
                  "retrieved_experiences": [entry["id"] for entry in experiences],
                  "selected_execution_id": selected_probe.execution.execution_id if selected_probe.execution else None,
                  "selected_harness_version": selected_harness.version,
                  "deliverable": selected_probe.execution.deliverable if selected_probe.execution else "",
                  "steps": [step.model_dump(mode="json") for step in steps],
                  "reflection": reflection,
                  "library_entry": library_entry["id"] if library_entry else None}
        unique_runs = {probe.execution.execution_id: probe.execution for probe in all_probes
                       if probe.execution is not None}
        result["metrics"] = {
            "executions": len(unique_runs),
            "model_tokens": {key: sum(record.token_usage.get(key, 0) for record in unique_runs.values())
                             for key in {key for record in unique_runs.values() for key in record.token_usage}},
            "latency_seconds": sum(record.latency for record in unique_runs.values()),
            "tool_calls": sum(len(record.tool_calls) for record in unique_runs.values()),
            "harness_modifications": sum(len(candidate.changes) for candidate in all_candidates.values()),
            "candidate_failures": sum(not candidate.valid for candidate in all_candidates.values()),
            "execution_failures": sum(record.status != "completed" for record in unique_runs.values()),
        }
        result["stages"] = ["TASK RECEIVED", "BASE EXECUTION", "INVARIANT PROPOSAL",
                            "DOMAIN PROPOSAL", "CANDIDATE PROBES", "BEHAVIORAL CONTRAST",
                            "COMPOSITION", "SUCCESSOR EXECUTION", "SELECTION",
                            "REFLECTION", "LIBRARY UPDATE" if library_entry else "NO LIBRARY ENTRY"]
        _write_checkpoint(task_root, result)
        await _emit(event_callback, "task.completed" if selected_probe.execution.status == "completed" else "task.failed",
                    task_id=task_id,
                    execution_id=result["selected_execution_id"],
                    library_entry=result["library_entry"])
        return result


def compare_runs(root: Path, first: str, second: str) -> dict:
    """Compare two persisted executions by ID without reading unrelated paths."""

    def read(run_id: str) -> dict:
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise ValueError("Run ID must be a 32-character hexadecimal identifier")
        matches = list(root.glob(f"*/{run_id}/execution.json"))
        if len(matches) != 1:
            raise FileNotFoundError(f"Run not found or ambiguous: {run_id}")
        return json.loads(matches[0].read_text(encoding="utf-8"))

    left, right = read(first), read(second)
    before = BehavioralAnalyzer.summarize(ExecutionRecord.model_validate(left))
    after = BehavioralAnalyzer.summarize(ExecutionRecord.model_validate(right))
    return {"run1": first, "run2": second, "before": before, "after": after,
            "changed_fields": [key for key in before if before[key] != after[key]]}
