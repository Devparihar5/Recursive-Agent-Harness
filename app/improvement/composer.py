"""Compose candidate edits with explicit evidence and conflict handling."""
from app.core.models import CompositionDecision
from .editors import HarnessEditor
from .utils import ask_json


class Composer:
    def __init__(self, provider, workspace):
        self.provider = provider
        self.editor = HarnessEditor(provider, workspace, "composer")

    async def compose(self, task, harness, candidates, probes):
        usable = {probe.candidate_id: probe for probe in probes if probe.execution is not None}
        supported = [candidate for candidate in candidates if candidate.valid and candidate.id in usable]
        if not supported:
            return None, CompositionDecision(accepted=False, component="harness", action="DROP",
                rationale="Composition requires a valid probed candidate", evidence=[], harness_path=None)
        decision = await ask_json(self.provider,
            "Determine whether complementary harness changes should be composed. "
            "Return {accepted:boolean,rationale:string,evidence:[observed facts],"
            "candidate_ids:[ids],conflicts:[conflicts],decisions:[{component,action,"
            "source_candidate,evidence:[observed facts],rationale}]}. Each component "
            "is a harness file path. Action must be KEEP, DROP, REVISE, or MERGE. "
            "Record one decision for every changed component, including dropped changes. "
            "source_candidate identifies a supplied candidate. Quote evidence exactly from "
            "probe evidence strings. Accept only when evidence "
            "supports complementary changes and conflicts can be resolved. Selection "
            "does not prove improvement; the composed harness will require its own probe.",
            {"task": task, "candidates": supported, "probes": probes})
        ids = decision.get("candidate_ids", [])
        known = {candidate.id for candidate in supported}
        observed = {item for probe in probes for item in probe.evidence}
        evidence = [str(item) for item in decision.get("evidence", [])]
        component_decisions = []
        changed = {patch["path"] for candidate in supported for patch in candidate.changes}
        for item in decision.get("decisions", []):
            if (not isinstance(item, dict) or item.get("action") not in {"KEEP", "DROP", "REVISE", "MERGE"}
                    or item.get("component") not in changed or item.get("source_candidate") not in known
                    or not item.get("evidence")
                    or any(fact not in observed for fact in item["evidence"])):
                raise ValueError("Component decisions require valid actions, candidates, and quoted evidence")
            component_decisions.append(CompositionDecision(**item,
                accepted=item["action"] != "DROP"))
        covered = {item.component for item in component_decisions}
        accepted = (decision.get("accepted") is True and bool(ids)
                    and set(ids).issubset(known) and bool(decision.get("evidence")))
        accepted = (accepted and all(item in observed for item in evidence)
                    and changed.issubset(covered)
                    and any(item.accepted for item in component_decisions))
        if not accepted:
            return None, CompositionDecision(accepted=False,
                component="harness", action="DROP", component_decisions=component_decisions,
                rationale=str(decision.get("rationale", "Insufficient composition evidence")),
                evidence=evidence, harness_path=None)
        chosen = [candidate for candidate in supported if candidate.id in ids]
        composed = await self.editor.edit(task, harness,
            {"composition_decision": decision, "candidate_patches": chosen, "probes": probes}, [])
        permitted = {item.component for item in component_decisions if item.accepted}
        if any(patch.get("path") not in permitted for patch in composed.changes):
            composed.valid = False
            composed.validation_errors.append("Composition edited a component without an accepted decision")
        return composed, CompositionDecision(accepted=composed.valid,
            rationale=str(decision.get("rationale", "")), evidence=evidence,
            component="harness", action="MERGE" if composed.valid else "DROP",
            component_decisions=component_decisions,
            selected_candidate_ids=ids,
            harness_path=composed.harness_path if composed.valid else None)
