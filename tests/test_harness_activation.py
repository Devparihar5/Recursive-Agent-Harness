import asyncio
import json
from pathlib import Path

from app.core.config import Settings
from app.core.models import Task
from app.executor.executor import AgentExecutor
from app.harness.loader import load_harness
from app.harness.model import harness_sha256
from app.llm.base import ModelResponse


def _harness(tmp_path: Path, name: str = "base") -> Path:
    root = tmp_path / name
    root.mkdir()
    for filename in ("systemprompt.md", "guardrails.md", "LongTermMEMORY.md", "tool_guidance.md"):
        (root / filename).write_text("# Instruction\nComplete the task.\n", encoding="utf-8")
    return root


def _trusted(root: Path, max_steps: int = 3) -> Settings:
    return Settings(max_steps=max_steps, allow_unsafe_harness_code=True,
                    trusted_harness_sha256=[harness_sha256(load_harness(root).files)])


class ActionThenFinish:
    def __init__(self, action: dict, answer: str = "done"):
        self.action = action
        self.answer = answer

    async def generate(self, messages, temperature=0, response_format=None):
        value = self.action if len(messages) == 2 else {"action": "final", "content": self.answer}
        return ModelResponse(content=json.dumps(value))


def test_harness_script_is_callable_from_saved_snapshot(tmp_path):
    root = _harness(tmp_path)
    script = root / "scripts" / "greet.py"
    script.parent.mkdir()
    script.write_text("print('hello from harness')\n", encoding="utf-8")
    executor = AgentExecutor(ActionThenFinish({"action": "run_script", "path": "scripts/greet.py"}),
                             tmp_path / "runs", _trusted(root))

    record = asyncio.run(executor.execute(Task(description="Run helper"), load_harness(root)))

    assert record.status == "completed"
    assert record.tool_calls[0]["result"]["success"] is True
    assert "hello from harness" in record.tool_calls[0]["result"]["stdout"]
    assert (Path(record.run_dir) / "harness" / "scripts" / "greet.py").is_file()


def test_plugin_blocks_tool_call_automatically(tmp_path):
    root = _harness(tmp_path)
    plugin = root / "plugins" / "guard.py"
    plugin.parent.mkdir()
    plugin.write_text(
        "def before_tool_call(context):\n"
        "    if context['action']['action'] == 'write_file':\n"
        "        return {'block': True, 'reason': 'writes blocked by plugin'}\n"
        "    return {}\n", encoding="utf-8")
    executor = AgentExecutor(ActionThenFinish({"action": "write_file", "path": "output/no.txt",
                                               "content": "do not write"}),
                             tmp_path / "runs", _trusted(root))

    record = asyncio.run(executor.execute(Task(description="Write a file"), load_harness(root)))

    assert record.status == "completed"
    assert "writes blocked by plugin" in record.tool_calls[0]["error"]
    assert not (Path(record.run_dir) / "workspace" / "output" / "no.txt").exists()
    assert any(event.get("event") == "plugin_hook" and event.get("hook") == "before_tool_call"
               for event in record.trajectory)


def test_plugin_can_veto_final_answer_until_revised(tmp_path):
    root = _harness(tmp_path)
    plugin = root / "plugins" / "final_check.py"
    plugin.parent.mkdir()
    plugin.write_text(
        "def before_task_complete(context):\n"
        "    if context['deliverable'] == 'draft':\n"
        "        return {'block': True, 'reason': 'revise draft'}\n"
        "    return {}\n", encoding="utf-8")

    class RevisingProvider:
        async def generate(self, messages, temperature=0, response_format=None):
            answer = "draft" if len(messages) == 2 else "final answer"
            return ModelResponse(content=json.dumps({"action": "final", "content": answer}))

    record = asyncio.run(AgentExecutor(RevisingProvider(), tmp_path / "runs", _trusted(root))
                         .execute(Task(description="Finish"), load_harness(root)))

    assert record.status == "completed"
    assert record.deliverable == "final answer"
    assert "revise draft" in record.tool_calls[0]["error"]


def test_plugin_failure_fails_execution_closed(tmp_path):
    root = _harness(tmp_path)
    plugin = root / "plugins" / "broken.py"
    plugin.parent.mkdir()
    plugin.write_text("def before_model_call(context):\n    raise RuntimeError('hook failed')\n",
                      encoding="utf-8")
    record = asyncio.run(AgentExecutor(ActionThenFinish({"action": "final", "content": "done"}),
                                       tmp_path / "runs", _trusted(root, 2))
                         .execute(Task(description="Finish"), load_harness(root)))

    assert record.status == "failed"
    assert "hook failed" in record.error


def test_concurrent_executions_use_their_own_harness_scripts(tmp_path):
    harnesses = []
    for label in ("first", "second"):
        root = _harness(tmp_path, label)
        script = root / "scripts" / "identity.py"
        script.parent.mkdir()
        script.write_text(f"print('{label}')\n", encoding="utf-8")
        harnesses.append(load_harness(root))
    shared = AgentExecutor(ActionThenFinish({"action": "run_script", "path": "scripts/identity.py"}),
                           tmp_path / "runs", Settings(max_steps=3, allow_unsafe_harness_code=True,
                           trusted_harness_sha256=[harness_sha256(harness.files) for harness in harnesses]))

    async def run_both():
        return await asyncio.gather(*(
            shared.execute(Task(description=f"Run {label}"), harness)
            for label, harness in zip(("first", "second"), harnesses)
        ))

    records = asyncio.run(run_both())
    assert [record.status for record in records] == ["completed", "completed"]
    assert [record.tool_calls[0]["result"]["stdout"].strip() for record in records] == ["first", "second"]


def test_harness_plugin_code_is_disabled_by_default(tmp_path):
    root = _harness(tmp_path)
    plugin = root / "plugins" / "guard.py"
    plugin.parent.mkdir()
    plugin.write_text("def before_model_call(context):\n    return {}\n", encoding="utf-8")
    record = asyncio.run(AgentExecutor(ActionThenFinish({"action": "final", "content": "done"}),
                                       tmp_path / "runs", Settings(max_steps=2))
                         .execute(Task(description="Finish"), load_harness(root)))
    assert record.status == "failed"
    assert "approved harness SHA-256" in record.error


def test_opt_in_does_not_trust_modified_harness(tmp_path):
    root = _harness(tmp_path)
    plugin = root / "plugins" / "guard.py"
    plugin.parent.mkdir()
    plugin.write_text("def before_model_call(context):\n    return {}\n", encoding="utf-8")
    settings = _trusted(root, 2)
    plugin.write_text("def before_model_call(context):\n    raise RuntimeError('must not run')\n", encoding="utf-8")
    record = asyncio.run(AgentExecutor(ActionThenFinish({"action": "final", "content": "done"}),
                                       tmp_path / "runs", settings)
                         .execute(Task(description="Finish"), load_harness(root)))
    assert record.status == "failed"
    assert "approved harness SHA-256" in record.error
