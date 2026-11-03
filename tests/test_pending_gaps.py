import asyncio
import base64
import json
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.api.dashboard import register_dashboard_api
from app.core.config import Settings, get_settings
from app.core.models import ExecutionRecord, HarnessCandidate, ProbeResult, Task
from app.harness.loader import load_harness
from app.improvement.composer import Composer
from app.improvement.editors import HarnessEditor
from app.improvement.recursion import ImprovementEngine
from app.llm.base import ModelResponse
from app.orchestration.pipeline import compare_runs


def test_completed_job_closes_event_stream(tmp_path):
    class Service:
        workspace_root = tmp_path

        async def run_base(self, task, event_callback=None):
            return {"deliverable": "done", "selected_execution_id": "execution"}

    app = FastAPI()
    register_dashboard_api(app, Service())
    with TestClient(app) as client:
        task_id = client.post("/api/tasks", json={"description": "Test"}).json()["task_id"]
        run_id = client.post(f"/api/tasks/{task_id}/run", json={"mode": "base", "k": 0}).json()["run_id"]
        with client.stream("GET", f"/api/runs/{run_id}/stream") as response:
            events = "".join(response.iter_text())
        assert "event: result" in events
        assert client.get(f"/api/runs/{run_id}").json()["status"] == "completed"


def test_source_upload_accepts_text_and_pdf(tmp_path):
    app = FastAPI()
    service = SimpleNamespace(workspace_root=tmp_path / "runs", config=SimpleNamespace(source_root=tmp_path))
    register_dashboard_api(app, service)
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    with TestClient(app) as client:
        task_id = client.post("/api/tasks", json={"description": "Test"}).json()["task_id"]
        response = client.post(f"/api/tasks/{task_id}/sources", json={"files": [
            {"name": "source.txt", "content": "evidence"},
            {"name": "source.pdf", "content_base64": base64.b64encode(buffer.getvalue()).decode()},
        ]})
    assert response.status_code == 200
    assert (tmp_path / "runs" / task_id / "sources" / "source.txt").read_text() == "evidence"
    assert (tmp_path / "runs" / task_id / "sources" / "source.pdf").read_bytes().startswith(b"%PDF-")


def test_compare_runs_validates_identifiers_and_compares_records(tmp_path):
    first, second = "a" * 32, "b" * 32
    for identifier, output in ((first, "before"), (second, "after")):
        path = tmp_path / "task" / identifier
        path.mkdir(parents=True)
        (path / "execution.json").write_text(ExecutionRecord(execution_id=identifier, output=output).model_dump_json())
    assert "deliverable" in compare_runs(tmp_path, first, second)["changed_fields"]
    with pytest.raises(ValueError):
        compare_runs(tmp_path, "../invalid", second)
    with pytest.raises(FileNotFoundError):
        compare_runs(tmp_path, "c" * 32, second)


def test_editor_retries_invalid_response_then_returns_invalid_candidate(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    for name in ("systemprompt.md", "guardrails.md", "LongTermMEMORY.md", "tool_guidance.md"):
        (base / name).write_text("Instruction", encoding="utf-8")

    class Provider:
        calls = 0
        async def generate(self, messages, temperature=0, response_format=None):
            self.calls += 1
            return ModelResponse(content='{"patches": []}')

    provider = Provider()
    candidate = asyncio.run(HarnessEditor(provider, tmp_path / "candidates").edit(
        "task", load_harness(base), [], []))
    assert provider.calls == 2
    assert candidate.valid is False
    assert len(candidate.validation_errors) == 2


def test_invalid_editors_fall_back_to_base_successor(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    for name in ("systemprompt.md", "guardrails.md", "LongTermMEMORY.md", "tool_guidance.md"):
        (base / name).write_text("Instruction", encoding="utf-8")

    class Provider:
        async def generate(self, messages, temperature=0, response_format=None):
            value = ({"evidence": [], "failures": [], "successful_behaviors": []}
                     if "Analyze the observed execution" in messages[0]["content"] else {"patches": []})
            return ModelResponse(content=json.dumps(value))

    class Executor:
        calls = 0
        async def execute(self, task, harness):
            self.calls += 1
            return ExecutionRecord(execution_id=uuid4().hex, output="base", deliverable="base", status="completed")

    executor = Executor()
    steps = asyncio.run(ImprovementEngine(Provider(), executor, tmp_path / "candidates").parallel_round(
        Task(description="Test"), load_harness(base), [], 1))
    assert executor.calls == 2
    assert steps[0].successor_harness == str(base)
    assert steps[0].accepted is False
    assert all(not candidate.valid for candidate in steps[0].candidates)


def test_composer_rejects_unobserved_evidence(tmp_path):
    class Provider:
        async def generate(self, messages, temperature=0, response_format=None):
            return ModelResponse(content=json.dumps({"accepted": True, "candidate_ids": ["c"],
                "evidence": ["invented"], "decisions": [{"component": "guardrails.md",
                "action": "KEEP", "source_candidate": "c", "evidence": ["invented"]}]}))

    candidate = HarnessCandidate(id="c", valid=True, changes=[{"path": "guardrails.md"}])
    probe = ProbeResult(candidate_id="c", execution=ExecutionRecord(), evidence=["observed"])
    with pytest.raises(ValueError, match="quoted evidence"):
        asyncio.run(Composer(Provider(), tmp_path).compose("task", None, [candidate], [probe]))


def test_nonsecret_settings_round_trip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_MAX_STEPS", raising=False)
    app = FastAPI()
    service = SimpleNamespace(workspace_root=tmp_path / "runs", config=Settings(), provider=None)
    register_dashboard_api(app, service)
    with TestClient(app) as client:
        response = client.put("/api/settings", json={"model": "local-test-model", "max_steps": 17})
        assert response.status_code == 200
        assert client.get("/api/settings").json()["model"] == "local-test-model"
    loaded = get_settings()
    assert loaded.model == "local-test-model"
    assert loaded.max_steps == 17


def test_api_key_is_session_only_and_existing_env_is_preserved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env_path = tmp_path / ".env"
    original = b"# keep this comment\r\nLLM_MODEL=old-model\r\nLLM_API_KEY=existing-key\r\nOTHER=value\r\n"
    env_path.write_bytes(original)
    app = FastAPI()
    service = SimpleNamespace(workspace_root=tmp_path / "runs", config=Settings(api_key="existing-key"), provider=None)
    register_dashboard_api(app, service)
    with TestClient(app) as client:
        response = client.put("/api/settings", json={"api_key": "session-secret"})
        assert response.status_code == 200
        assert response.json()["has_api_key"] is True
        assert "api_key" not in response.json()
        assert env_path.read_bytes() == original
        response = client.put("/api/settings", json={"model": "new-model", "api_key": "new-session-secret"})
        assert response.status_code == 200
    saved = env_path.read_bytes()
    assert b"# keep this comment\r\n" in saved
    assert b"LLM_API_KEY=existing-key\r\n" in saved
    assert b"LLM_MODEL=new-model\r\n" in saved
    assert b"new-session-secret" not in saved
    assert service.config.api_key == "new-session-secret"
