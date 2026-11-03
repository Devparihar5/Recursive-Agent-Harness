import asyncio
import json

from app.core.config import Settings
from app.core.models import Task
from app.executor.executor import AgentExecutor
from app.harness.loader import load_harness
from app.llm.base import ModelResponse


def test_on_demand_skill_and_isolated_read_only_subagent(tmp_path):
    root = tmp_path / "base"
    root.mkdir()
    for name in ("systemprompt.md", "guardrails.md", "LongTermMEMORY.md", "tool_guidance.md"):
        (root / name).write_text("PARENT PRIVATE INSTRUCTIONS\n", encoding="utf-8")
    skill = root / "skills" / "review" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("Triggers: review\nCheck the evidence.\n", encoding="utf-8")
    agent = root / "sub_agents" / "researcher" / "AGENT.md"
    agent.parent.mkdir(parents=True)
    agent.write_text("# Researcher\nTools: read_file\nInspect the named file.\n", encoding="utf-8")
    (tmp_path / "source.txt").write_text("Source evidence", encoding="utf-8")
    child_messages = []

    class Provider:
        async def generate(self, messages, temperature=0, response_format=None):
            if messages[0]["content"].startswith("# Researcher"):
                child_messages.append([dict(message) for message in messages])
                action = ({"action": "read_file", "path": "source.txt"} if len(messages) == 2
                          else {"action": "final", "content": "Evidence inspected"})
            else:
                assert "Check the evidence." not in messages[0]["content"]
                action = ({"action": "skill", "name": "review"} if len(messages) == 2 else
                          {"action": "delegate", "name": "researcher", "task": "Read source.txt"}
                          if len(messages) == 4 else {"action": "final", "content": "done"})
            return ModelResponse(content=json.dumps(action))

    record = asyncio.run(AgentExecutor(Provider(), tmp_path / "runs",
        Settings(source_root=tmp_path, max_steps=5)).execute(
            Task(description="Review source", source_files=["source.txt"]), load_harness(root)))
    assert record.status == "completed"
    assert "Check the evidence." in record.tool_calls[0]["result"]["content"]
    assert record.tool_calls[1]["result"]["content"] == "Evidence inspected"
    assert "PARENT PRIVATE INSTRUCTIONS" not in json.dumps(child_messages)
    assert "Source evidence" in json.dumps(child_messages)
    assert any(event.get("event") == "subagent_tool_call" and
               event.get("result", {}).get("content") == "Source evidence"
               for event in record.trajectory)


def test_subagent_cannot_write_or_delegate_without_permission(tmp_path):
    root = tmp_path / "base"
    root.mkdir()
    for name in ("systemprompt.md", "guardrails.md", "LongTermMEMORY.md", "tool_guidance.md"):
        (root / name).write_text("Instruction\n", encoding="utf-8")
    agent = root / "sub_agents" / "reader" / "AGENT.md"
    agent.parent.mkdir(parents=True)
    agent.write_text("# Reader\nTools: read_file\n", encoding="utf-8")

    class Provider:
        async def generate(self, messages, temperature=0, response_format=None):
            if messages[0]["content"].startswith("# Reader"):
                action = ({"action": "write_file", "path": "output/forbidden.txt", "content": "x"}
                          if len(messages) == 2 else {"action": "final", "content": "blocked"})
            else:
                action = ({"action": "delegate", "name": "reader", "task": "Inspect"}
                          if len(messages) == 2 else {"action": "final", "content": "done"})
            return ModelResponse(content=json.dumps(action))

    record = asyncio.run(AgentExecutor(Provider(), tmp_path / "runs", Settings(max_steps=4))
                         .execute(Task(description="Test"), load_harness(root)))
    assert record.status == "completed"
    assert not (tmp_path / "runs" / record.execution_id / "workspace" / "output" / "forbidden.txt").exists()
    assert record.tool_calls[0]["result"]["content"] == "blocked"
