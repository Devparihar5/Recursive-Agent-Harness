"""Shared, serializable records for harness experiments."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Record(BaseModel):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class SubAgentDefinition(Record):
    name: str
    instructions: str
    triggers: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)


class Task(Record):
    id: str = Field(default_factory=lambda: uuid4().hex)
    task_id: str = ""
    description: str = ""
    domain: str = "general"
    source_files: list[str] = Field(default_factory=list)
    prompt: str = ""
    input: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.prompt or self.description or self.input


class ExecutionRecord(Record):
    execution_id: str = ""
    deliverable: str = ""
    finished_at: str | None = None
    latency: float = 0
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    id: str = Field(default_factory=lambda: uuid4().hex)
    task_id: str = ""
    harness_version: str = ""
    model: str = ""
    status: str = "pending"
    output: str = ""
    error: str | None = None
    started_at: str = Field(default_factory=utc_now)
    completed_at: str | None = None
    duration_ms: float = 0
    token_usage: dict[str, Any] = Field(default_factory=dict)
    trajectory: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    run_dir: str = ""


class HarnessCandidate(Record):
    candidate_id: str = ""
    scope: str = ""
    base_harness_version: str = ""
    modified_harness_path: str = ""
    diff: str = ""
    reasoning: str = ""
    id: str = Field(default_factory=lambda: uuid4().hex)
    path: str = ""
    version: str = ""
    parent_version: str | None = None
    description: str = ""
    harness_path: str = ""
    editor: str = ""
    changes: list[dict[str, Any]] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    valid: bool = True


class ProbeResult(Record):
    candidate_id: str = ""
    task_id: str = ""
    candidate: HarnessCandidate | None = None
    execution_record: ExecutionRecord | None = None
    behavioral_observations: list[str] = Field(default_factory=list)
    feedback: str = ""
    execution: ExecutionRecord | None = None
    evidence: list[str] = Field(default_factory=list)


class CompositionDecision(Record):
    component: str = ""
    action: str = ""
    source_candidate: str | None = None
    accepted: bool = False
    evidence: list[str] = Field(default_factory=list)
    harness_path: str | None = None
    selected_candidate_ids: list[str] = Field(default_factory=list)
    rationale: str = ""
    changes: dict[str, str] = Field(default_factory=dict)


class ImprovementStep(Record):
    reference_executions: list[ExecutionRecord] = Field(default_factory=list)
    candidate_harnesses: list[HarnessCandidate] = Field(default_factory=list)
    probe_results: list[ProbeResult] = Field(default_factory=list)
    composition_decisions: list[CompositionDecision] = Field(default_factory=list)
    successor_harness: str | None = None
    successor_execution: ExecutionRecord | None = None
    round_id: str = Field(default_factory=lambda: uuid4().hex)
    baseline: ExecutionRecord | None = None
    candidates: list[HarnessCandidate] = Field(default_factory=list)
    composition: CompositionDecision | None = None
    selected_candidate_id: str | None = None
    reflection: dict[str, Any] = Field(default_factory=dict)
    iteration: int = 0
    parent_version: str = ""
    candidate_version: str = ""
    selected_version: str = ""
    accepted: bool = False
    rationale: str = ""
    probes: list[ProbeResult] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)
