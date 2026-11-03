import asyncio
import json

import pytest

from app.benchmark.verifier import ModelJudgeVerifier
from app.llm.base import ModelResponse


class JudgeProvider:
    def __init__(self, content):
        self.content = content
        self.messages = None

    async def generate(self, messages, temperature=0, response_format=None):
        self.messages = messages
        assert response_format == {"type": "json_object"}
        return ModelResponse(content=self.content, model="judge-model")


def test_model_judge_uses_only_public_task_output_and_private_rubric():
    provider = JudgeProvider(json.dumps({
        "score": 0.8, "label": "partial", "rationale": "Mostly complete",
    }))
    result = asyncio.run(ModelJudgeVerifier(provider).verify(
        "task-1", "Draft answer", "Write a reply", {"rubric": "Mention refund"}))

    assert result == {"score": 0.8, "label": "partial", "kind": "model_assessment",
                      "model": "judge-model", "details": {"rationale": "Mostly complete"}}
    supplied = json.loads(provider.messages[1]["content"])
    assert supplied == {"task": "Write a reply", "response": "Draft answer",
                        "rubric": "Mention refund"}
    assert "harness" not in provider.messages[1]["content"]


def test_model_judge_rejects_invalid_scores():
    provider = JudgeProvider('{"score": 2, "label": "pass", "rationale": "ok"}')
    with pytest.raises(ValueError, match="score"):
        asyncio.run(ModelJudgeVerifier(provider).verify("task-1", "Answer", "Task", {}))
