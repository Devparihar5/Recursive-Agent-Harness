import asyncio
import json

from app.core.models import ExecutionRecord, ProbeResult, Task
from app.improvement.probe import BehavioralAnalyzer
from app.improvement.utils import data
from app.llm.base import ModelResponse


def test_analysis_uses_observed_summary_without_full_trajectory():
    class CapturingProvider:
        async def generate(self, messages, temperature=0, response_format=None):
            self.payload = json.loads(messages[1]["content"])
            return ModelResponse(content=json.dumps({
                "evidence": ["A source was inspected"],
                "failures": [], "successful_behaviors": ["Inspected source"],
            }))

    record = ExecutionRecord(status="completed", output="Evidence-based answer",
        tool_calls=[{"action": {"action": "read_file", "path": "source.txt"},
                     "result": {"content": "Source data"}}],
        trajectory=[{"event": "model_request", "messages": ["x" * 20000]}])
    provider = CapturingProvider()
    result = asyncio.run(BehavioralAnalyzer(provider).analyze(
        Task(description="Review the source"), record))

    assert "trajectory" not in provider.payload
    assert "x" * 20000 not in json.dumps(provider.payload)
    assert provider.payload["behavioral_contrast"]["candidate"]["files_read"] == ["source.txt"]
    assert result["contrast"]["candidate"]["deliverable"] == "Evidence-based answer"


def test_model_payload_compacts_nested_probe_records():
    execution = ExecutionRecord(status="completed", output="Answer",
        trajectory=[{"messages": ["x" * 20000]}],
        tool_calls=[{"action": {"action": "read_file", "path": "source.txt"},
                     "result": {"content": "y" * 20000}}])
    probe = ProbeResult(candidate_id="candidate-1", execution=execution,
                        execution_record=execution, evidence=["Exact observed fact"])

    payload = data({"probes": [probe]})

    assert payload["probes"][0]["candidate_id"] == "candidate-1"
    assert payload["probes"][0]["evidence"] == ["Exact observed fact"]
    assert "execution_record" not in payload["probes"][0]
    assert "trajectory" not in payload["probes"][0]["execution"]
    assert "x" * 20000 not in json.dumps(payload)
    assert "y" * 20000 not in json.dumps(payload)
