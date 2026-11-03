from types import SimpleNamespace
from pathlib import Path
import json
import pytest

from app.core.models import Task
from app.library.embeddings import EmbeddingClient
from app.library.retrieval import hybrid_rank, rank
from app.library.store import ImprovementLibrary


def _entry(entry_id: str, domain: str, task_shape: str, components: list, cue: str,
           created_at: str = "2026-01-01T00:00:00") -> dict:
    return {
        "id": entry_id,
        "created_at": created_at,
        "domain": domain,
        "task_shape": task_shape,
        "components": components,
        "experience": {"cue": cue, "lesson": cue, "evidence": [cue]},
        "harness_path": "/tmp/library/harness",
    }


def _task(domain: str = "customer_support", task_shape: str = "support_ticket",
         description: str = "Refund policy guidance") -> dict:
    return {
        "domain": domain,
        "task_shape": task_shape,
        "metadata": {},
        "components": [],
        "description": description,
    }


def test_rank_orders_entries_by_domain_shape_and_keyword_overlap() -> None:
    task = _task()
    entries = [
        _entry("a" * 32, "billing", "refund_policy", [], "refund policy"),
        _entry("b" * 32, "customer_support", "support_ticket", [], "refund policy"),
    ]
    ranked = rank(entries, task, limit=3)
    assert [entry["id"] for entry in ranked] == ["b" * 32, "a" * 32]


def test_rank_respects_limit() -> None:
    task = _task()
    entries = [
        _entry(f"{index:032x}", "customer_support", "support_ticket", [], "refund policy")
        for index in range(5)
    ]
    assert len(rank(entries, task, limit=2)) == 2
    assert len(rank(entries, task, limit=99)) == 5


def test_hybrid_rank_falls_back_to_keyword_ranking_without_vector_results() -> None:
    task = _task()
    entries = [_entry("b" * 32, "customer_support", "support_ticket", [], "refund policy")]
    assert hybrid_rank([], entries, task, limit=3) == rank(entries, task, limit=3)


def test_hybrid_rank_merges_vector_similarity_with_keyword_tiebreak() -> None:
    task = _task()
    strong = _entry("b" * 32, "customer_support", "support_ticket", [], "refund policy")
    weak = _entry("a" * 32, "billing", "refund_policy", [], "refund policy")
    merged = hybrid_rank(
        [{**strong, "_vector_score": 0.9}, {**weak, "_vector_score": 0.2}],
        [strong, weak],
        task,
        limit=3,
    )
    assert merged[0]["id"] == "b" * 32
    assert "_vector_score" not in merged[0]
    assert "relevance" in merged[0]


def test_embedding_client_text_builders() -> None:
    entry_text = EmbeddingClient.entry_text({
        "domain": "customer_support",
        "task_shape": "support_ticket",
        "components": ["guardrails.md"],
        "experience": {"cue": "refund policy", "lesson": "Require refunds", "evidence": ["refund policy"]},
    })
    assert "refund policy" in entry_text
    assert "customer_support" in entry_text

    task = Task(description="Refund policy guidance", domain="customer_support",
                metadata={"task_shape": "support_ticket"})
    query_text = EmbeddingClient.task_text(task)
    assert "Refund policy guidance" in query_text
    assert "support_ticket" in query_text


def test_pending_library_entry_lifecycle(tmp_path: Path) -> None:
    library = ImprovementLibrary(tmp_path / "library")
    harness_dir = tmp_path / "harness_snapshot"
    harness_dir.mkdir()
    (harness_dir / "systemprompt.md").write_text("# Instruction\nInspect sources.\n", encoding="utf-8")
    harness = SimpleNamespace(path=str(harness_dir), version="v1")
    pending = library.add_pending(
        harness,
        {"cue": "refund policy", "lesson": "Require refunds", "evidence": ["refund policy"]},
        domain="customer_support",
        task_shape="support_ticket",
    )
    assert pending["status"] == "pending"
    assert len(library.list_pending()) == 1
    adopted = library.adopt(pending["id"], note="Reviewed evidence")
    assert adopted is not None
    assert adopted["adopted_from"] == pending["id"]
    assert library.list_pending() == []
    assert library.get(adopted["id"]) is not None
    assert library.get(adopted["id"])["adopted_from"] == pending["id"]
    assert library.get(adopted["id"])["experience"]["adoption_note"] == "Reviewed evidence"


def test_failed_adoption_keeps_pending_entry(tmp_path: Path, monkeypatch) -> None:
    library = ImprovementLibrary(tmp_path / "library")
    harness_dir = tmp_path / "snapshot"
    harness_dir.mkdir()
    (harness_dir / "systemprompt.md").write_text("Instructions", encoding="utf-8")
    pending = library.add_pending(SimpleNamespace(path=harness_dir, version="v1"),
                                  {"lesson": "Inspect evidence"}, "general", "general")
    def fail(*args, **kwargs):
        raise RuntimeError("index unavailable")
    monkeypatch.setattr(library, "add", fail)
    with pytest.raises(RuntimeError, match="index unavailable"):
        library.adopt(pending["id"])
    assert library.list_pending()[0]["id"] == pending["id"]
    assert Path(pending["harness_path"]).is_dir()


def test_library_search_and_diff_against_base(tmp_path: Path, monkeypatch) -> None:
    from app.harness.loader import load_harness

    base = tmp_path / "base"
    changed = tmp_path / "changed"
    for root in (base, changed):
        root.mkdir()
        for name in ("systemprompt.md", "guardrails.md", "LongTermMEMORY.md", "tool_guidance.md"):
            (root / name).write_text("Base instruction\n", encoding="utf-8")
    (changed / "guardrails.md").write_text("Inspect sources\n", encoding="utf-8")
    library = ImprovementLibrary(tmp_path / "library")
    entry = library.add(load_harness(changed), {"lesson": "Inspect sources",
                        "components": ["guardrails.md"]}, "support", "ticket")
    assert [item["id"] for item in library.search_entries("inspect", "support", "guardrails")] == [entry["id"]]
    assert library.search_entries(domain="operations") == []
    diff = library.diff_from_base(entry["id"], base)
    assert "-Base instruction" in diff and "+Inspect sources" in diff
    library.annotate(entry["id"], "First review")
    library.annotate(entry["id"], "Second review")
    assert {item["note"] for item in library.get(entry["id"])["annotations"]} == {"First review", "Second review"}
    assert library.archive(entry["id"], "Not currently useful")["archived"] is True
    assert library.get(entry["id"]) is None
    assert Path(entry["harness_path"]).is_dir()
    library.embedder = SimpleNamespace(embed=lambda text: [1.0])
    monkeypatch.setattr(library.index, "search", lambda *args, **kwargs: [{**entry, "_vector_score": 1.0}])
    assert library.retrieve(Task(description="Inspect sources", domain="support")) == []
    domain_index = Path(entry["entry_path"]).parent / "INDEX.json"
    assert json.loads(domain_index.read_text(encoding="utf-8")) == []
    assert library.search_entries(include_archived=True)[0]["archived"] is True
    assert library.restore(entry["id"])["archived"] is False
    assert library.get(entry["id"]) is not None
    assert len(json.loads(domain_index.read_text(encoding="utf-8"))[0]["annotations"]) == 2
    def fail_index(*args, **kwargs):
        raise OSError("index write failed")
    monkeypatch.setattr(library, "_write_domain_index", fail_index)
    with pytest.raises(OSError, match="index write failed"):
        library.archive(entry["id"])
    assert library.get(entry["id"]) is not None
    with pytest.raises(OSError, match="index write failed"):
        library.annotate(entry["id"], "Not committed")
    assert len(library.get(entry["id"])["annotations"]) == 2
