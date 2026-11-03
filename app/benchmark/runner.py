"""Benchmark runner — external task-quality evaluation kept strictly outside the improvement loop.

Architecture
------------
The BenchmarkRunner sits OUTSIDE the Pipeline. It:
  1. Runs the pipeline (or a base-only execution) to produce a deliverable.
  2. Passes the deliverable + task to an ExternalVerifier (user-supplied).
  3. Records the score in a separate benchmark_results/ directory.
  4. Never exposes the score, rubric, ground-truth, or grader output to the
     pipeline, editors, selector, or reflector.

The ExternalVerifier protocol is intentionally minimal. Users implement it
to wrap whatever judge they have (LLM judge, test harness, unit tests, etc.).

Usage
-----
    from app.benchmark.runner import BenchmarkRunner, ExternalVerifier
    from app.orchestration.pipeline import Pipeline

    class MyJudge(ExternalVerifier):
        async def verify(self, task_id, deliverable, task_text, metadata):
            # call your judge, return a score between 0 and 1
            score = await my_llm_judge(deliverable, metadata["rubric"])
            return {"score": score, "label": "pass" if score > 0.7 else "fail"}

    runner = BenchmarkRunner(pipeline=Pipeline(), verifier=MyJudge())
    result = await runner.run_task(task, mode="base",
                                   verification_context={"rubric": private_rubric})
    print(result["benchmark"]["score"])  # never seen by pipeline
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ExternalVerifier protocol — implement this to plug in any judge
# ---------------------------------------------------------------------------

class ExternalVerifier(Protocol):
    """Interface for external task-quality judges.

    Implementations MUST NOT read from the improvement library or receive
    any harness state, candidate info, or retrieval context. They only see
    the task description and the deliverable produced by the agent.
    """

    async def verify(
        self,
        task_id: str,
        deliverable: str,
        task_text: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Evaluate the deliverable and return a score record.

        Returns a dict with at minimum:
            {"score": float,        # 0.0–1.0
             "label": str,          # "pass" / "fail" / "partial" etc.
             "details": dict}       # any extra judge output
        The returned dict must NOT contain rubrics, ground truth, or any
        information that would give the improvement loop an unfair signal.
        """
        ...


# ---------------------------------------------------------------------------
# Null verifier — always returns 0.0 with a clear warning
# ---------------------------------------------------------------------------

class NullVerifier:
    """Placeholder verifier that returns no score.

    Replace with a real ExternalVerifier implementation to get scores.
    """

    async def verify(self, task_id, deliverable, task_text, metadata):
        log.warning(
            "BenchmarkRunner: NullVerifier is active. No real score was computed. "
            "Implement ExternalVerifier and pass it to BenchmarkRunner."
        )
        return {
            "score": None,
            "label": "unverified",
            "details": {"reason": "No verifier configured. Implement ExternalVerifier."},
        }


# ---------------------------------------------------------------------------
# BenchmarkRunner
# ---------------------------------------------------------------------------

class BenchmarkRunner:
    """Run a task through the pipeline and score the result externally.

    The runner enforces a strict firewall: pipeline result is used only to
    extract the deliverable string, which is passed to the verifier. The
    verifier's output is stored separately and never fed back into the pipeline.
    """

    def __init__(
        self,
        pipeline=None,
        verifier: ExternalVerifier | None = None,
        results_root: Path | str = "benchmark_results",
    ):
        self.pipeline = pipeline
        self.verifier = verifier or NullVerifier()
        self.results_root = Path(results_root)
        self.results_root.mkdir(parents=True, exist_ok=True)

    async def run_task(
        self,
        task,
        mode: str = "base",
        k: int = 1,
        event_callback=None,
        verification_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the task through the pipeline, then score via the external verifier.

        Parameters
        ----------
        task        : Task object with description, domain, source_files, etc.
        mode        : "base" for baseline only, "parallel"/"sequential" for improvement.
        k           : Width/depth for improvement mode (1–5).
        event_callback : Optional callback, forwarded to the pipeline.
        verification_context : Private verifier inputs, never sent to the pipeline.

        Returns a result dict with pipeline_result (deliverable, metrics) and
        benchmark (score, label, details), both persisted to benchmark_results/.
        """
        if mode not in {"base", "parallel", "sequential"}:
            raise ValueError("mode must be base, parallel, or sequential")
        if mode != "base" and (type(k) is not int or not 1 <= k <= 5):
            raise ValueError("k must be an integer from 1 to 5")
        if self.pipeline is None:
            raise ValueError("A pipeline is required to run a new benchmark task")
        # The verifier's private context is never attached to the task sent
        # into the pipeline or to its event stream.
        pipeline_task = task.model_copy(deep=True)
        forbidden = ("answer", "ground_truth", "score", "grader", "rubric",
                     "benchmark", "label", "expected_output", "hidden")
        pipeline_task.metadata = {
            key: value for key, value in pipeline_task.metadata.items()
            if not any(word in key.casefold() for word in forbidden)
        }

        # --- Run pipeline ---
        if mode == "base":
            pipeline_result = await self.pipeline.run_base(
                pipeline_task, event_callback=event_callback
            )
        else:
            pipeline_result = await self.pipeline.run(
                pipeline_task, mode=mode, k=k, event_callback=event_callback
            )

        return await self.verify_completed(task, pipeline_result,
                                           verification_context=verification_context)

    async def verify_completed(self, task, pipeline_result: dict,
                               verification_context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Score an already completed run without executing the pipeline again."""
        task_id = pipeline_result.get("task_id", "")
        deliverable = pipeline_result.get("deliverable", "")
        mode = pipeline_result.get("mode", "base")
        k = pipeline_result.get("k", 0)
        if not task_id or not deliverable or not pipeline_result.get("selected_execution_id"):
            raise ValueError("A completed run with a deliverable is required")
        if mode != "base" and pipeline_result.get("_checkpoint_stage"):
            raise ValueError("Improvement run has not reached its final result")

        # --- Firewall: extract only what the verifier needs ---
        task_text = getattr(task, "text", "") or getattr(task, "description", "")
        # --- External verification ---
        try:
            benchmark = await self.verifier.verify(
                task_id=task_id,
                deliverable=deliverable,
                task_text=task_text,
                metadata=dict(verification_context or {}),
            )
            score = benchmark.get("score")
            if (score is not None and
                    (isinstance(score, bool) or not isinstance(score, (int, float))
                     or not math.isfinite(score) or not 0 <= score <= 1)):
                raise ValueError("Verifier score must be between 0 and 1, or None")
        except Exception as exc:
            log.error("BenchmarkRunner: verifier raised %s: %s", type(exc).__name__, exc)
            benchmark = {
                "score": None,
                "label": "error",
                "details": {"error": str(exc)},
            }

        # --- Persist result separately from the pipeline record ---
        result = {
            "task_id": task_id,
            "run_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "k": k,
            "pipeline_summary": {
                "selected_execution_id": pipeline_result.get("selected_execution_id"),
                "harness_version": pipeline_result.get("selected_harness_version"),
                "metrics": pipeline_result.get("metrics", {}),
            },
            "benchmark": benchmark,
            # Deliverable stored so the benchmark record is self-contained.
            # It is NOT fed back into the pipeline.
            "deliverable": deliverable,
        }

        self._persist(task_id, result)
        return result

    def list_results(self, task_id: str | None = None) -> list[dict]:
        """List all benchmark results, optionally filtered by task_id."""
        return list_benchmark_results(self.results_root, task_id)

    def _persist(self, task_id: str, result: dict) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        filename = f"benchmark_{ts}_{uuid4().hex[:8]}.json"
        path = self.results_root / filename
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(path)
        log.info("BenchmarkRunner: result persisted to %s", path)


def list_benchmark_results(results_root: Path | str, task_id: str | None = None) -> list[dict]:
    """Read persisted external scores without invoking a verifier or pipeline."""
    root = Path(results_root)
    if not root.is_dir():
        return []
    results = []
    for path in sorted(root.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("benchmark"), dict):
                if task_id is None or data.get("task_id") == task_id:
                    results.append(data)
        except (OSError, ValueError):
            log.warning("Skipping unreadable benchmark result: %s", path)
    return results
