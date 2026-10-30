"""Local API factory."""
from app.orchestration.pipeline import Pipeline


def create_app(pipeline=None):
    from fastapi import FastAPI
    from app.api.dashboard import register_dashboard_api
    app = FastAPI(title="Recursive Agent Harness")
    register_dashboard_api(app, pipeline or Pipeline())
    return app
