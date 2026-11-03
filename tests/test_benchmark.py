import asyncio

from app.benchmark.runner import BenchmarkRunner
from app.core.models import Task


class RecordingPipeline:
    def __init__(self):
        self.tasks = []

    async def run_base(self, task, *, event_callback=None):
        self.tasks.append(task.model_copy(deep=True))
        return {"task_id": task.task_id, "deliverable": "answer",
                "selected_execution_id": "execution-1", "metrics": {}}


class RecordingVerifier:
    def __init__(self):
        self.calls = []

    async def verify(self, task_id, deliverable, task_text, metadata):
        self.calls.append((task_id, deliverable, task_text, metadata))
        return {"score": 1.0 if deliverable == metadata["expected"] else 0.0,
                "label": "pass"}


def test_benchmark_keeps_private_verification_data_outside_pipeline(tmp_path):
    pipeline = RecordingPipeline()
    verifier = RecordingVerifier()
    runner = BenchmarkRunner(pipeline, verifier, tmp_path / "results")
    task = Task(task_id="task-one", description="Reply to customer",
                metadata={"domain_note": "support", "hidden_answer": "secret"})

    result = asyncio.run(runner.run_task(
        task, verification_context={"expected": "answer", "rubric": "private"}))

    assert pipeline.tasks[0].metadata == {"domain_note": "support"}
    assert task.metadata["hidden_answer"] == "secret"
    assert verifier.calls == [("task-one", "answer", "Reply to customer",
                               {"expected": "answer", "rubric": "private"})]
    assert result["benchmark"]["score"] == 1.0
    assert "rubric" not in str(pipeline.tasks[0].model_dump())
    assert runner.list_results("task-one") == [result]


def test_benchmark_results_do_not_overwrite_same_task(tmp_path):
    runner = BenchmarkRunner(RecordingPipeline(), RecordingVerifier(), tmp_path)
    task = Task(task_id="same-task", description="Reply")
    for _ in range(2):
        asyncio.run(runner.run_task(task, verification_context={"expected": "answer"}))
    assert len(runner.list_results("same-task")) == 2


def test_benchmark_rejects_invalid_mode_before_pipeline(tmp_path):
    pipeline = RecordingPipeline()
    runner = BenchmarkRunner(pipeline, RecordingVerifier(), tmp_path)
    try:
        asyncio.run(runner.run_task(Task(task_id="bad"), mode="unknown"))
    except ValueError:
        pass
    else:
        raise AssertionError("invalid mode was accepted")
    assert pipeline.tasks == []
