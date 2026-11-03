"""Run a sequence of tasks while retaining one improvement library."""
from __future__ import annotations
from app.orchestration.pipeline import _safe_id


async def run_stream(pipeline, tasks, *, mode: str = "parallel", k: int = 1,
                     adopt_supported: bool = False) -> list[dict]:
    """Run tasks sequentially; adoption requires an explicit caller choice."""
    if mode not in {"parallel", "sequential"} or type(k) is not int or not 1 <= k <= 5:
        raise ValueError("mode must be parallel or sequential, with k from 1 to 5")
    tasks = list(tasks)
    identifiers = [_safe_id(task.task_id or task.id) for task in tasks]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Stream task identifiers must be unique")
    results = []
    for task in tasks:
        result = await pipeline.run(task, mode=mode, k=k)
        if adopt_supported and result.get("library_entry"):
            adopted = pipeline.library.adopt(result["library_entry"], note="Adopted by stream runner")
            if adopted is None:
                raise ValueError("Pending stream entry could not be adopted")
            result = {**result, "adopted_library_entry": adopted["id"]}
        results.append(result)
    return results
