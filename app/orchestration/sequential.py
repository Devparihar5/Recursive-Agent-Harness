"""Sequential exploration entry point."""
from app.harness.loader import load_harness


async def run_sequential(engine, task, harness, experiences, k: int):
    steps = []
    current = harness
    for _ in range(k):
        step = (await engine.single_round(task, current, history=steps,
                                          experiences=experiences))[0]
        steps.append(step)
        current = load_harness(step.successor_harness or current.path)
    return steps
