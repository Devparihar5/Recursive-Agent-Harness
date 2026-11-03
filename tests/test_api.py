import asyncio
import json
from types import SimpleNamespace

import pytest


def test_health_endpoint_does_not_require_model_connection(tmp_path):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.api.routes import create_app

    app = create_app(type("Service", (), {"workspace_root": tmp_path})())
    with TestClient(app) as client:
        for path in ("/health", "/api/health"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}


def test_evaluation_returns_saved_benchmarks_separately_from_run_metrics(tmp_path):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.api.routes import create_app

    results_root = tmp_path / "benchmarks"
    results_root.mkdir()
    (results_root / "result.json").write_text(json.dumps({
        "task_id": "task-1", "run_at": "2026-11-03T00:00:00+00:00",
        "mode": "base", "benchmark": {"score": 0.75, "label": "partial"},
    }), encoding="utf-8")
    (results_root / "invalid.json").write_text("not json", encoding="utf-8")
    pipeline_root = tmp_path / "runs" / "task-2"
    pipeline_root.mkdir(parents=True)
    (pipeline_root / "pipeline.json").write_text(json.dumps({
        "task_id": "task-2", "mode": "base", "selected_execution_id": "execution-2",
        "deliverable": "Completed output", "metrics": {"executions": 1},
        "_checkpoint_stage": "base_done",
    }), encoding="utf-8")
    service = SimpleNamespace(workspace_root=tmp_path / "runs",
                              config=SimpleNamespace(benchmark_results_root=results_root))
    with TestClient(create_app(service)) as client:
        response = client.get("/api/evaluation")

    assert response.status_code == 200
    assert response.json()["benchmark_results"] == [{
        "task_id": "task-1", "run_at": "2026-11-03T00:00:00+00:00",
        "mode": "base", "benchmark": {"score": 0.75, "label": "partial"},
    }]
    assert response.json()["runs"][0]["selected_execution_id"] == "execution-2"
    assert response.json()["metrics"] == [{"executions": 1}]


def test_verify_completed_task_stores_score_without_restarting_pipeline(tmp_path, monkeypatch):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.api.routes import create_app
    from app.core.config import Settings

    task_id = "completed-task"
    task_root = tmp_path / "runs" / task_id
    task_root.mkdir(parents=True)
    (task_root / "task.json").write_text(json.dumps({
        "task_id": task_id, "description": "Reply to a customer",
    }), encoding="utf-8")
    pipeline_result = {"task_id": task_id, "mode": "base", "k": 0,
                       "selected_execution_id": "execution-1", "deliverable": "Reply",
                       "_checkpoint_stage": "base_done", "metrics": {"executions": 1}}
    pipeline_path = task_root / "pipeline.json"
    pipeline_path.write_text(json.dumps(pipeline_result), encoding="utf-8")
    seen = []

    class Verifier:
        async def verify(self, task_id, deliverable, task_text, metadata):
            seen.append((task_id, deliverable, task_text, metadata))
            return {"score": 0.7, "label": "partial", "kind": "model_assessment",
                    "details": {"rationale": "Adequate reply"}}

    monkeypatch.setattr("app.benchmark.verifier.create_model_verifier", lambda config: Verifier())
    service = SimpleNamespace(workspace_root=tmp_path / "runs",
                              config=Settings(benchmark_results_root=tmp_path / "benchmarks"))
    with TestClient(create_app(service)) as client:
        first = client.post(f"/api/tasks/{task_id}/verify", json={"rubric": "Be concise"})
        second = client.post(f"/api/tasks/{task_id}/verify", json={"rubric": "Be concise"})
        evaluation = client.get("/api/evaluation")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert seen == [(task_id, "Reply", "Reply to a customer", {"rubric": "Be concise"})]
    assert evaluation.json()["benchmark_results"][0]["benchmark"]["score"] == 0.7
    assert json.loads(pipeline_path.read_text(encoding="utf-8")) == pipeline_result
    assert "Be concise" not in pipeline_path.read_text(encoding="utf-8")


def test_examples_include_runnable_objectives_and_sources(tmp_path):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.api.dashboard import register_dashboard_api

    app = fastapi.FastAPI()
    register_dashboard_api(app, type("Service", (), {"workspace_root": tmp_path})())

    with TestClient(app) as client:
        response = client.get("/api/examples")

    assert response.status_code == 200
    examples = response.json()
    assert {example["id"] for example in examples} == {
        "quick-reply", "double-charge", "incident-review"
    }
    for example in examples:
        assert example["title"] and example["summary"] and example["description"]
        assert all(source["name"].endswith(".md") and source["content"]
                   for source in example["sources"])
    assert examples[0]["id"] == "quick-reply"
    assert examples[0]["sources"] == []
    assert all(example["sources"] for example in examples[1:])


def test_output_reports_pending_and_failed_jobs(tmp_path):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.api.dashboard import register_dashboard_api

    app = fastapi.FastAPI()
    register_dashboard_api(app, type("Service", (), {"workspace_root": tmp_path})())
    app.state.jobs.update({
        "a" * 32: {"run_id": "a" * 32, "status": "running", "events": []},
        "b" * 32: {
            "run_id": "b" * 32,
            "status": "failed",
            "events": [{"type": "error", "error": "Pipeline failed"}],
        },
    })

    with TestClient(app) as client:
        pending = client.get(f"/api/runs/{'a' * 32}/output")
        failed = client.get(f"/api/runs/{'b' * 32}/output")

    assert pending.status_code == 200
    assert pending.json() == {"deliverable": "", "status": "running", "error": None}
    assert failed.status_code == 200
    assert failed.json() == {"deliverable": "", "status": "failed", "error": "Pipeline failed"}


def test_cancel_run_persists_terminal_status_and_ends_stream(tmp_path):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.api.dashboard import register_dashboard_api

    class WaitingService:
        workspace_root = tmp_path

        async def run_base(self, task, event_callback=None):
            await asyncio.Event().wait()

    app = fastapi.FastAPI()
    register_dashboard_api(app, WaitingService())

    with TestClient(app) as client:
        task_id = client.post("/api/tasks", json={"description": "Wait"}).json()["task_id"]
        started = client.post(f"/api/tasks/{task_id}/run", json={"mode": "base", "k": 0})
        assert started.status_code == 200
        run_id = started.json()["run_id"]
        assert client.get(f"/api/runs/{run_id}").json()["mode"] == "base"

        cancelled = client.delete(f"/api/runs/{run_id}")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert client.get(f"/api/runs/{run_id}").json()["status"] == "cancelled"
        assert client.get(f"/api/runs/{run_id}/output").json() == {
            "deliverable": "", "status": "cancelled", "error": "Run cancelled"
        }
        with client.stream("GET", f"/api/runs/{run_id}/stream") as stream:
            assert "run.cancelled" in "".join(stream.iter_text())

    assert (tmp_path / task_id / "jobs" / f"{run_id}.json").is_file()


def test_stale_running_job_becomes_persisted_interruption(tmp_path):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.api.dashboard import register_dashboard_api

    task_id, run_id = "task", "a" * 32
    job_path = tmp_path / task_id / "jobs" / f"{run_id}.json"
    job_path.parent.mkdir(parents=True)
    job_path.write_text(json.dumps({
        "run_id": run_id, "task_id": task_id, "status": "running", "events": []
    }), encoding="utf-8")

    app = fastapi.FastAPI()
    register_dashboard_api(app, type("Service", (), {"workspace_root": tmp_path})())

    with TestClient(app) as client:
        assert client.get(f"/api/runs/{run_id}").json()["status"] == "interrupted"
        assert client.get(f"/api/runs/{run_id}/output").json() == {
            "deliverable": "", "status": "interrupted",
            "error": "Run was interrupted before completion"
        }

    saved = json.loads(job_path.read_text(encoding="utf-8"))
    assert saved["status"] == "interrupted"
    assert saved["events"][-1]["type"] == "run.interrupted"
