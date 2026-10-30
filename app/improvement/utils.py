"""Small serialization helpers for model-mediated improvement."""
import json


def data(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
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
