import asyncio
from types import SimpleNamespace

import pytest

from app.core.models import Task
from app.orchestration.stream import run_stream


def test_stream_runs_in_order_and_adopts_only_when_requested():
    events = []

    class Library:
        def adopt(self, entry_id, note=""):
            events.append(("adopt", entry_id))
            return {"id": "adopted-" + entry_id}

    class Pipeline:
        library = Library()

        async def run(self, task, *, mode, k):
            events.append(("run", task.task_id, mode, k))
            return {"task_id": task.task_id, "library_entry": task.task_id}

    tasks = [Task(task_id="a"), Task(task_id="b")]
    result = asyncio.run(run_stream(Pipeline(), tasks, mode="sequential", k=2,
                                    adopt_supported=True))
    assert events == [("run", "a", "sequential", 2), ("adopt", "a"),
                      ("run", "b", "sequential", 2), ("adopt", "b")]
    assert result[0]["adopted_library_entry"] == "adopted-a"


def test_stream_rejects_duplicate_ids_before_running():
    with pytest.raises(ValueError, match="unique"):
        asyncio.run(run_stream(SimpleNamespace(), [Task(task_id="same"), Task(task_id="same")]))
