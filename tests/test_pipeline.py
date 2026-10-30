import asyncio
import json

from app.core.config import Settings
from app.core.models import Task
from app.harness.loader import load_harness
from app.llm.base import ModelResponse
from app.orchestration.pipeline import Pipeline


class ScriptedProvider:
    async def generate(self, messages, temperature=0, response_format=None):
        instruction = messages[0]["content"]
        payload = json.loads(messages[1]["content"]) if response_format else None
        if "Improve a complete agent harness" in instruction:
            value = {"patches": [{"path": "guardrails.md", "content": "# Guardrails\nInspect every source.\n"}],
                     "reasoning": "Require inspection"}
        elif "Analyze the observed execution" in instruction:
            value = {"evidence": ["The run inspected a source file."],
                     "failures": [], "successful_behaviors": ["Source inspection"]}
        elif "Determine whether complementary" in instruction:
            value = {"accepted": False, "candidate_ids": [], "evidence": [], "rationale": "No isolated gain"}
        elif "Select the best execution" in instruction:
            value = {"selected": payload["choices"][0]["label"], "rationale": "Complete"}
        elif "Attribute observed behavior" in instruction:
            value = {"attributions": [], "lesson": "NO_ENTRY", "summary": "Insufficient isolation"}
        elif len(messages) == 2:
            value = {"action": "read_file", "path": "source.txt"}
        else:
            value = {"action": "final", "content": "Reviewed the supplied source."}
        return ModelResponse(content=json.dumps(value), token_usage={"completion_tokens": 1})


def test_two_tasks_reset_to_common_base(tmp_path):
    base = tmp_path / "harnesses" / "base"
    base.mkdir(parents=True)
    for name in ("systemprompt.md", "guardrails.md", "LongTermMEMORY.md", "tool_guidance.md"):
        (base / name).write_text("# Instruction\nInspect evidence.\n", encoding="utf-8")
    (tmp_path / "source.txt").write_text("Order record", encoding="utf-8")
    version = load_harness(base).version
    settings = Settings(harnesses_root=base.parent, source_root=tmp_path, max_steps=3)
    pipeline = Pipeline(settings, provider=ScriptedProvider(),
                        library_root=tmp_path / "library", workspace_root=tmp_path / "runs")
    task_a = Task(task_id="a", description="Review source", source_files=["source.txt"])
    task_b = Task(task_id="b", description="Review another source", source_files=["source.txt"])
    first = asyncio.run(pipeline.run(task_a, mode="parallel", k=1))
    second = asyncio.run(pipeline.run(task_b, mode="sequential", k=1))
    assert first["base_harness_version"] == version
    assert second["base_harness_version"] == version
    assert first["deliverable"] == "Reviewed the supplied source."
    assert second["library_entry"] is None
    assert len(first["steps"][0]["reference_executions"]) == 1
    assert len(first["steps"][0]["candidate_harnesses"]) == 2


def test_parallel_width_and_sequential_depth(tmp_path):
    base = tmp_path / "harnesses" / "base"
    base.mkdir(parents=True)
    for name in ("systemprompt.md", "guardrails.md", "LongTermMEMORY.md", "tool_guidance.md"):
        (base / name).write_text("# Instruction\nInspect evidence.\n", encoding="utf-8")
    (tmp_path / "source.txt").write_text("Order record", encoding="utf-8")
    settings = Settings(harnesses_root=base.parent, source_root=tmp_path, max_steps=3)
    pipeline = Pipeline(settings, provider=ScriptedProvider(),
                        library_root=tmp_path / "library", workspace_root=tmp_path / "runs")
    parallel = asyncio.run(pipeline.run(Task(task_id="parallel", description="Review source",
        source_files=["source.txt"]), mode="parallel", k=3))
    sequential = asyncio.run(pipeline.run(Task(task_id="sequential", description="Review source",
        source_files=["source.txt"]), mode="sequential", k=3))
    assert len(parallel["steps"]) == 3
    assert parallel["metrics"]["executions"] == 12
    assert all(len(step["reference_executions"]) == 3 for step in parallel["steps"])
    assert all(len(step["candidate_harnesses"]) == 6 for step in parallel["steps"])
    assert len(sequential["steps"]) == 3
    assert sequential["metrics"]["executions"] == 12
    assert all(len(step["reference_executions"]) == 1 for step in sequential["steps"])


class LearningProvider(ScriptedProvider):
    async def generate(self, messages, temperature=0, response_format=None):
        instruction = messages[0]["content"]
        payload = json.loads(messages[1]["content"]) if response_format else None
        if "Select the best execution" in instruction:
            candidate = next(choice for choice in payload["choices"]
                             if choice["deliverable"] == "candidate")
            return ModelResponse(content=json.dumps({"selected": candidate["label"],
                                                     "rationale": "Inspected source"}))
        if "Attribute observed behavior" in instruction:
            selected = payload["selected_candidate_id"]
            evidence = next(probe["evidence"][0] for probe in payload["probes"]
                            if probe["candidate_id"] == selected)
            return ModelResponse(content=json.dumps({
                "attributions": [{"component": "guardrails.md", "candidate": selected,
                                  "change": "Require source inspection", "observed_behavior": evidence,
                                  "verdict": "HELPED"}],
                "lesson": {"cue": "Tasks with supplied records",
                           "lesson": "Require source inspection in guardrails",
                           "evidence": evidence, "confidence": "medium"},
                "summary": "Observed source inspection"}))
        if response_format is None and len(messages) > 2:
            value = "candidate" if "Inspect every source." in instruction else "base"
            return ModelResponse(content=json.dumps({"action": "final", "content": value}))
        return await super().generate(messages, temperature, response_format)


def test_experience_retrieval_does_not_replace_base_harness(tmp_path):
    base = tmp_path / "harnesses" / "base"
    base.mkdir(parents=True)
    for name in ("systemprompt.md", "guardrails.md", "LongTermMEMORY.md", "tool_guidance.md"):
        (base / name).write_text("# Instruction\nInspect evidence.\n", encoding="utf-8")
    (tmp_path / "source.txt").write_text("Order record", encoding="utf-8")
    original_version = load_harness(base).version
    settings = Settings(harnesses_root=base.parent, source_root=tmp_path, max_steps=3)
    pipeline = Pipeline(settings, provider=LearningProvider(),
                        library_root=tmp_path / "library", workspace_root=tmp_path / "runs")
    first = asyncio.run(pipeline.run(Task(task_id="first", description="Review source",
        domain="customer_support", source_files=["source.txt"]), mode="parallel", k=1))
    assert first["library_entry"]
    assert first["deliverable"] == "candidate"
    stored = pipeline.library.get(first["library_entry"])
    assert (tmp_path / "library" / "customer_support" / "entry_001" /
            "harness" / "guardrails.md").is_file()
    second = asyncio.run(pipeline.run(Task(task_id="second", description="Review source again",
        domain="customer_support", source_files=["source.txt"]), mode="parallel", k=1))
    assert second["base_harness_version"] == original_version
    assert first["library_entry"] in second["retrieved_experiences"]
    assert stored["version"] != original_version
