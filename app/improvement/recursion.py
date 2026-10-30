"""Bounded contrast rounds; orchestration owns terminal selection and reflection."""
import asyncio
import inspect
from pathlib import Path
from uuid import uuid4

from app.core.models import HarnessCandidate, ImprovementStep
from .composer import Composer
from .editors import DomainEditor, InvariantEditor
from .probe import ProbeRunner


class ImprovementEngine:
    def __init__(self, provider, executor, workspace, event_callback=None):
        self.provider = provider
        self.executor = executor
        self.workspace = Path(workspace)
        self.prober = ProbeRunner(provider, executor)
        self.event_callback = event_callback

    async def _emit(self, event_type, **fields):
        if self.event_callback is None:
            return
        result = self.event_callback({"type": event_type, **fields})
        if inspect.isawaitable(result):
            await result

    async def single_round(self, task, harness, history=None, experiences=None, candidate_count=1):
        return await self.parallel_round(task, harness, experiences or [], candidate_count,
                                         history=history)

    async def parallel_round(self, task, harness, experiences, k, history=None):
        if k < 1:
            raise ValueError("k must be positive")
        round_id = uuid4().hex
        root = self.workspace / round_id
        baselines = [HarnessCandidate(id=f"baseline-{index}-{round_id}",
            candidate_id=f"baseline-{index}-{round_id}", harness_path=str(harness.path),
            modified_harness_path=str(harness.path), version=harness.version,
            editor="baseline", changes=[], valid=True) for index in range(k)]
        await self._emit("probe.started", phase="base", count=k)
        references = await asyncio.gather(*(self.prober.run(task, item) for item in baselines))
        await self._emit("probe.completed", phase="base", count=k)
        context = {"prior_history": history or [], "reference_executions": references}
        editors = [editor_type(self.provider, root) for _ in range(k)
                   for editor_type in (InvariantEditor, DomainEditor)]
        await self._emit("proposal.started", count=2 * k)
        candidates = await asyncio.gather(*(editor.edit(task, harness, context, experiences)
                                            for editor in editors))
        await self._emit("proposal.completed", count=len(candidates),
                         candidate_ids=[item.id for item in candidates])
        await self._emit("probe.started", phase="candidates", count=len(candidates))
        probes = await asyncio.gather(*(self.prober.run(task, candidate, references[index // 2].execution)
                                       for index, candidate in enumerate(candidates)))
        await self._emit("probe.completed", phase="candidates", count=len(probes))
        pool = [*references, *probes]
        await self._emit("composition.started", count=k)
        compositions = await asyncio.gather(*(Composer(self.provider, root).compose(
            task, harness, candidates, pool) for _ in range(k)))
        await self._emit("composition.completed", count=k,
                         accepted=sum(decision.accepted for _, decision in compositions))
        successors = [candidate if candidate is not None and candidate.valid else baselines[index]
                      for index, (candidate, _) in enumerate(compositions)]
        await self._emit("probe.started", phase="successors", count=k)
        successor_probes = await asyncio.gather(*(self.prober.run(task, candidate, references[index].execution)
                                                  for index, candidate in enumerate(successors)))
        await self._emit("probe.completed", phase="successors", count=k)
        steps = []
        for index, ((composed, decision), successor, result) in enumerate(
                zip(compositions, successors, successor_probes)):
            step_candidates = [*candidates, *([composed] if composed is not None else [])]
            step_probes = [*pool, result]
            steps.append(ImprovementStep(round_id=f"{round_id}-{index}",
                baseline=references[index].execution,
                reference_executions=[item.execution for item in references if item.execution],
                candidates=step_candidates, candidate_harnesses=step_candidates,
                probes=step_probes, probe_results=step_probes,
                composition=decision,
                composition_decisions=getattr(decision, "component_decisions", None) or [decision],
                successor_harness=successor.harness_path, successor_execution=result.execution,
                parent_version=harness.version, candidate_version=successor.version,
                selected_version=successor.version, accepted=decision.accepted,
                rationale=decision.rationale))
        return steps
