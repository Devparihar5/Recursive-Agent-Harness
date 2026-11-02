"""Small serialization helpers for model-mediated improvement."""
import json


def data(value):
    if hasattr(value, "model_dump"):
        return data(value.model_dump(mode="json"))
    if isinstance(value, dict):
        if {"execution_id", "trajectory", "tool_calls"}.issubset(value):
            actions = []
            for call in value.get("tool_calls", []):
                action = call.get("action", {})
                if isinstance(action, dict):
                    action = {key: action[key] for key in ("action", "path") if key in action}
                actions.append({"step": call.get("step"), "action": action,
                                "error": call.get("error")})
            return {"execution_id": value.get("execution_id"),
                    "harness_version": value.get("harness_version"),
                    "status": value.get("status"),
                    "deliverable": value.get("deliverable") or value.get("output"),
                    "error": value.get("error"), "latency": value.get("latency"),
                    "token_usage": data(value.get("token_usage", {})),
                    "tool_calls": actions}
        if {"candidate_id", "execution_record", "evidence"}.issubset(value):
            return {"candidate_id": value.get("candidate_id"),
                    "evidence": data(value.get("evidence", [])),
                    "execution": data(value.get("execution") or value.get("execution_record"))}
        if {"round_id", "probe_results"}.issubset(value):
            return {key: data(value.get(key)) for key in (
                "round_id", "reference_executions", "candidate_harnesses",
                "probe_results", "composition_decisions", "successor_harness",
                "selected_candidate_id", "accepted", "rationale")}
        return {str(k): data(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [data(item) for item in value]
    return str(value) if not isinstance(value, (str, int, float, bool, type(None))) else value


async def ask_json(provider, instruction, payload):
    response = await provider.generate(
        [{"role": "system", "content": instruction + " Return a JSON object only."},
         {"role": "user", "content": json.dumps(data(payload))}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    result = json.loads(response.content)
    if not isinstance(result, dict):
        raise ValueError("Model response must be a JSON object")
    return result
