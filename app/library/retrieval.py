"""Deterministic top-three retrieval by domain, task shape, and components."""
import dataclasses
import re


def terms(value) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value).lower()))


def task_data(task) -> dict:
    if isinstance(task, dict):
        return task
    if dataclasses.is_dataclass(task):
        return dataclasses.asdict(task)
    if hasattr(task, "model_dump"):
        return task.model_dump()
    return vars(task)


def rank(entries: list[dict], task, limit: int = 3) -> list[dict]:
    data = task_data(task)
    domain = str(data.get("domain", "")).casefold()
    metadata = data.get("metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    shape = str(data.get("task_shape", metadata.get("task_shape", ""))).casefold()
    keywords = terms(data)
    components = terms(data.get("components", metadata.get("components", [])))
    ranked = []
    for entry in entries:
        relevance = 10 * bool(domain and domain == entry["domain"].casefold())
        relevance += 6 * bool(shape and shape == entry["task_shape"].casefold())
        relevance += 4 * len(components & terms(entry.get("components", [])))
        relevance += len(keywords & terms(entry.get("experience", {})))
        ranked.append({**entry, "relevance": relevance})
    ranked.sort(key=lambda entry: (entry["relevance"], entry["created_at"], entry["id"]), reverse=True)
    return ranked[:max(0, min(limit, 3))]
