import asyncio
import json
from types import SimpleNamespace

from app.improvement.composer import Composer
from app.llm.base import ModelResponse


def test_composer_receives_prior_history_and_adopted_experience(tmp_path):
    seen = {}

    class Provider:
        async def generate(self, messages, temperature=0, response_format=None):
            seen.update(json.loads(messages[1]["content"]))
            return ModelResponse(content=json.dumps({"accepted": False, "candidate_ids": [],
                                                      "evidence": [], "decisions": []}))

    candidate = SimpleNamespace(id="candidate", valid=True, changes=[{"path": "guardrails.md"}])
    probe = SimpleNamespace(candidate_id="candidate", execution=object(), evidence=[])
    asyncio.run(Composer(Provider(), tmp_path).compose(
        "task", None, [candidate], [probe], history=[{"round": 1}],
        experiences=[{"lesson": "Inspect sources"}]))
    assert seen["history"] == [{"round": 1}]
    assert seen["experiences"] == [{"lesson": "Inspect sources"}]
