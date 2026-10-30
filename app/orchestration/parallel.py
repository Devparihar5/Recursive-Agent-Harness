"""Parallel exploration entry point."""
from app.improvement.recursion import ImprovementEngine


async def run_parallel(engine: ImprovementEngine, task, harness, experiences, k: int):
    return await engine.parallel_round(task, harness, experiences, k)
