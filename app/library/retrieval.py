"""Hybrid retrieval: vector similarity when embeddings are available, keyword fallback otherwise.

Ranking strategy
----------------
1. If the index returns vector-search results (embedding available):
   - Primary sort key: ``_vector_score`` (cosine similarity, higher = better)
   - Tie-break: keyword score (domain, task_shape, component overlap)
   - Returns the top ``limit`` entries from the combined score.

2. If vector search returns nothing (Ollama unavailable, cold start, zero vectors):
   - Falls back entirely to the existing keyword scorer.
   - This keeps the library useful even when the embedding service is down.

The limit is respected strictly — callers always get at most ``limit`` entries.
"""
from __future__ import annotations

import dataclasses
import re


# ---------------------------------------------------------------------------
# Helpers shared by both paths
# ---------------------------------------------------------------------------

def _terms(value) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value).lower()))


def _task_data(task) -> dict:
    if isinstance(task, dict):
        return task
    if dataclasses.is_dataclass(task):
        return dataclasses.asdict(task)
    if hasattr(task, "model_dump"):
        return task.model_dump()
    return vars(task)


def _keyword_score(entry: dict, domain: str, shape: str,
                   keywords: set[str], components: set[str]) -> float:
    score = 10.0 * bool(domain and domain == entry.get("domain", "").casefold())
    score += 6.0 * bool(shape and shape == entry.get("task_shape", "").casefold())
    score += 4.0 * len(components & _terms(entry.get("components", [])))
    score += float(len(keywords & _terms(entry.get("experience", {}))))
    return score


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rank(entries: list[dict], task, limit: int = 3) -> list[dict]:
    """Keyword-only rank — used as fallback and for callers without an index."""
    data = _task_data(task)
    domain = str(data.get("domain", "")).casefold()
    metadata = data.get("metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    shape = str(data.get("task_shape", metadata.get("task_shape", ""))).casefold()
    keywords = _terms(data)
    components = _terms(data.get("components", metadata.get("components", [])))

    ranked = []
    for entry in entries:
        score = _keyword_score(entry, domain, shape, keywords, components)
        ranked.append({**entry, "relevance": score})
    ranked.sort(key=lambda e: (e["relevance"], e.get("created_at", ""), e.get("id", "")), reverse=True)
    return ranked[:max(0, min(limit, len(ranked)))]


def hybrid_rank(
    vector_results: list[dict],
    all_entries: list[dict],
    task,
    limit: int = 3,
) -> list[dict]:
    """Combine vector similarity and keyword scores into a single ranked list.

    Parameters
    ----------
    vector_results : entries returned by LibraryIndex.search(), each carrying
                     a ``_vector_score`` key (cosine similarity 0–1).
    all_entries    : full list of entries from LibraryIndex.list_entries(),
                     used as fallback when vector_results is empty.
    task           : Task object or dict describing the current task.
    limit          : maximum number of entries to return.
    """
    if not vector_results:
        # Embedding unavailable — pure keyword fallback.
        return rank(all_entries, task, limit)

    data = _task_data(task)
    domain = str(data.get("domain", "")).casefold()
    metadata = data.get("metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    shape = str(data.get("task_shape", metadata.get("task_shape", ""))).casefold()
    keywords = _terms(data)
    components = _terms(data.get("components", metadata.get("components", [])))

    # Build a lookup so we can merge keyword scores into vector results.
    scored = []
    for entry in vector_results:
        v_score = float(entry.get("_vector_score", 0.0))
        k_score = _keyword_score(entry, domain, shape, keywords, components)
        # Combine: vector similarity is dominant; keyword breaks ties.
        # Normalise keyword score to [0, 1] range (max possible ≈ 21).
        combined = v_score + (k_score / 100.0)
        clean = {k: v for k, v in entry.items() if not k.startswith("_")}
        scored.append({**clean, "relevance": combined})

    scored.sort(key=lambda e: (e["relevance"], e.get("created_at", ""), e.get("id", "")), reverse=True)
    return scored[:max(0, min(limit, len(scored)))]
