"""Local API factory."""
from app.orchestration.pipeline import Pipeline
from fastapi import FastAPI
from app.api.dashboard import register_dashboard_api


def create_app(pipeline=None):
    app = FastAPI(title="Recursive Agent Harness")

    @app.get("/health")
    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    register_dashboard_api(app, pipeline or Pipeline())
    return app
