"""Evidence-linked credit attribution and reusable lessons."""
from .utils import ask_json


class Reflector:
    def __init__(self, provider):
        self.provider = provider

    async def reflect(self, task, candidates, probes, selected_candidate_id,
                      history=None, base_harness=None, selected_harness=None):
        result = await ask_json(self.provider,
            "Attribute observed behavior to candidate changes conservatively. "
            "Return {attributions:[{component,candidate,change,observed_behavior,verdict}],"
            "lesson:{cue,lesson,evidence,confidence} or \"NO_ENTRY\",summary:string}. "
            "Attribution verdict must be HELPED, HURT, NO_OBSERVED_EFFECT, or CONFOUNDED. "
            "Each observed_behavior must quote a supplied probe evidence string exactly; "
            "candidate must identify a supplied candidate. Return at most one lesson, "
            "and NO_ENTRY when evidence does not support a reusable lesson. Lesson evidence "
            "must quote a probe evidence string exactly. Distinguish inference "
            "from demonstrated causality. Include failed edits and transfer limits. "
            "Never claim a change caused success solely because it was selected.",
            {"task": task,
             "base_harness": base_harness.files if base_harness is not None else None,
             "selected_harness": selected_harness.files if selected_harness is not None else None,
             "candidates": candidates, "probes": probes,
             "composition_decisions": [decision for step in (history or [])
                                       for decision in step.composition_decisions],
             "selected_candidate_id": selected_candidate_id})
        lesson = result.get("lesson")
        if not isinstance(result.get("attributions"), list) or not (lesson == "NO_ENTRY" or isinstance(lesson, dict)):
            raise ValueError("Reflection requires attributions and one lesson or NO_ENTRY")
        known = {candidate.id for candidate in candidates}
        observed = {fact for probe in probes for fact in probe.evidence}
        for attribution in result["attributions"]:
            if (not isinstance(attribution, dict) or attribution.get("candidate") not in known
                    or attribution.get("observed_behavior") not in observed
                    or attribution.get("verdict") not in {"HELPED", "HURT", "NO_OBSERVED_EFFECT", "CONFOUNDED"}
                    or not attribution.get("component") or not attribution.get("change")):
                raise ValueError("Attribution must identify a candidate and quote observed evidence")
        if isinstance(lesson, dict) and (not all(key in lesson for key in ("cue", "lesson", "evidence", "confidence"))
                                         or lesson["evidence"] not in observed):
            raise ValueError("Lesson must include a cue, lesson, observed evidence, and confidence")
        return result
