import pytest


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
