import asyncio
import json
from pathlib import Path

from app.core.config import Settings
from app.core.models import Task
from app.executor.executor import AgentExecutor
from app.harness.loader import load_harness


class ReadThenFinish:
    async def generate(self, messages, temperature=0, response_format=None):
        from app.llm.base import ModelResponse
        if len(messages) == 2:
            content = {"action": "read_file", "path": "source.txt"}
        else:
            content = {"action": "final", "content": "Source inspected."}
        return ModelResponse(content=json.dumps(content), token_usage={"completion_tokens": 1})


def _base(tmp_path):
    root = tmp_path / "base"
    root.mkdir()
    for name in ("systemprompt.md", "guardrails.md", "LongTermMEMORY.md", "tool_guidance.md"):
        (root / name).write_text("# Instruction\nInspect sources.\n", encoding="utf-8")
    return root


def test_execution_records_source_inspection_and_snapshot(tmp_path):
    root = _base(tmp_path)
    (tmp_path / "source.txt").write_text("Account evidence", encoding="utf-8")
    task = Task(task_id="case", description="Review source", source_files=["source.txt"])
    settings = Settings(source_root=tmp_path, max_steps=3)
    record = asyncio.run(AgentExecutor(ReadThenFinish(), tmp_path / "runs", settings)
                         .execute(task, load_harness(root)))
    run = Path(record.run_dir)
    assert record.status == "completed"
    assert record.deliverable == "Source inspected."
    assert record.tool_calls[0]["action"]["action"] == "read_file"
    assert (run / "harness" / "systemprompt.md").is_file()
    assert (run / "trajectory.json").is_file()
    assert (run / "tool_calls.json").is_file()
    assert (run / "deliverable.md").read_text(encoding="utf-8") == record.deliverable


def test_harness_rejects_escape_and_missing_skill_trigger(tmp_path):
    from app.harness.loader import safe_path
    try:
        safe_path(tmp_path, "../outside")
    except ValueError:
        pass
    else:
        raise AssertionError("Path escape should be rejected")
    root = _base(tmp_path)
    skill = root / "skills" / "customer_issue_analysis"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Workflow\nInspect account.", encoding="utf-8")
    try:
        load_harness(root)
    except ValueError as exc:
        assert "trigger" in str(exc)
    else:
        raise AssertionError("Skill without trigger should be rejected")
    (skill / "SKILL.md").write_text("# Workflow\nTriggers: customer support\nInspect account.", encoding="utf-8")
    harness = load_harness(root)
    task = Task(description="Customer support case", domain="customer_support")
    assert "skills/customer_issue_analysis/SKILL.md" in harness.active_skills(task)
