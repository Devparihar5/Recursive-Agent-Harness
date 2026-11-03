"""Complete harness snapshots with embedding-based metadata retrieval."""
import json
import logging
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .embeddings import EmbeddingClient
from .index import LibraryIndex
from .retrieval import hybrid_rank

log = logging.getLogger(__name__)


class ImprovementLibrary:
    def __init__(self, root: Path, embedder: EmbeddingClient | None = None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self.index = LibraryIndex(self.root, embedder=embedder)

    def add(self, harness, experience: dict, domain: str, task_shape: str,
            version: str | None = None) -> dict:
        # Validate metadata before creating any persistent artifacts.
        experience = json.loads(json.dumps(experience, allow_nan=False))
        source = Path(getattr(harness, "path", harness)).resolve()
        if not source.is_dir():
            raise ValueError("Harness path must be a directory")
        if source == self.root or source in self.root.parents:
            raise ValueError("Library must be outside the harness directory")
        # Reject links rather than following them out of the harness boundary.
        for path in source.rglob("*"):
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError("Harness snapshots cannot contain symbolic links or junctions")
        entry_id = uuid.uuid4().hex
        domain_slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(domain)).strip("_") or "general"
        domain_root = self.root / domain_slug
        domain_root.mkdir(parents=True, exist_ok=True)
        sequence = 1
        while True:
            entry_root = domain_root / f"entry_{sequence:03d}"
            try:
                entry_root.mkdir()
                break
            except FileExistsError:
                sequence += 1
        target = entry_root / "harness"
        metadata = {
            "id": entry_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "version": str(version or getattr(harness, "version", "unknown")),
            "domain": str(domain),
            "task_shape": str(task_shape),
            "experience": experience,
            "components": experience.get("components", []) if isinstance(experience, dict) else [],
            "path": str(target),
            "harness_path": str(target),
            "entry_path": str(entry_root),
        }
        try:
            shutil.copytree(source, target)
            (entry_root / "EXPERIENCE.md").write_text(
                "# Improvement experience\n\n```json\n" + json.dumps(experience, indent=2) + "\n```\n",
                encoding="utf-8",
            )
            self.index.add(metadata)
            self._write_domain_index(domain_root, str(domain))
        except Exception:
            self.index.remove(entry_id)
            if entry_root.exists():
                shutil.rmtree(entry_root)
            raise
        return metadata

    def list_entries(self) -> list[dict]:
        return self.index.list_entries()

    def get(self, entry_id: str) -> dict | None:
        if re.fullmatch(r"[0-9a-f]{32}", entry_id):
            return self.index.get(entry_id)
        if re.fullmatch(r"entry_[0-9]{3,}", entry_id):
            matches = [entry for entry in self.list_entries()
                       if Path(entry["entry_path"]).name == entry_id]
            return matches[0] if len(matches) == 1 else None
        return None

    def retrieve(self, task, limit: int = 3) -> list[dict]:
        """Retrieve entries using hybrid ranking.

        1. Vector search first (if embedder is available)
        2. Fallback to keyword-only ranking if vector search returns nothing
        """
        all_entries = self.list_entries()
        vector_results: list[dict] = []

        if self.embedder is not None:
            try:
                query_text = EmbeddingClient.task_text(task)
                query_vector = self.embedder.embed(query_text)
                if query_vector:
                    vector_results = self.index.search(query_vector, limit=limit * 2)
                else:
                    log.debug("Library.retrieve: query embedding returned zeros, using keyword fallback")
            except Exception as exc:
                log.warning("Library.retrieve: vector search failed (%s), falling back to keyword", exc)
        else:
            log.debug("Library.retrieve: no embedder configured, using keyword ranking")

        # Hybrid rank when we have vector results, keyword fallback otherwise
        selected = hybrid_rank(vector_results, all_entries, task, limit)

        enriched = []
        for entry in selected:
            harness_root = Path(entry["harness_path"]).resolve()
            if not harness_root.is_relative_to(self.root) or not harness_root.is_dir():
                continue
            files = {}
            total = 0
            for path in harness_root.rglob("*"):
                if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                    raise ValueError("Library harness contains a link")
                if path.is_file():
                    total += path.stat().st_size
                    if total > 1024 * 1024:
                        raise ValueError("Library harness exceeds retrieval size limit")
                    files[path.relative_to(harness_root).as_posix()] = path.read_text(encoding="utf-8")
            enriched.append({**entry, "harness_files": files})
        return enriched

    def _write_domain_index(self, domain_root: Path, domain: str) -> None:
        entries = [entry for entry in self.list_entries() if entry["domain"] == domain]
        temporary = domain_root / "INDEX.json.tmp"
        temporary.write_text(json.dumps(entries, indent=2), encoding="utf-8")
        temporary.replace(domain_root / "INDEX.json")

    def add_pending(self, harness, experience: dict, domain: str, task_shape: str) -> dict:
        """Add a pending library entry that requires user adoption.

        Returns metadata with status='pending'. The entry is stored in a
        separate 'pending' directory until explicitly adopted.
        """
        import shutil

        experience = json.loads(json.dumps(experience, allow_nan=False))
        source = Path(harness.path).resolve()
        if not source.is_dir():
            raise ValueError("Harness path must be a directory")
        if source == self.root or source in self.root.parents:
            raise ValueError("Library must be outside the harness directory")
        for path in source.rglob("*"):
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError("Harness snapshots cannot contain symbolic links or junctions")

        entry_id = uuid.uuid4().hex
        pending_root = self.root / "pending"
        pending_root.mkdir(parents=True, exist_ok=True)
        entry_root = pending_root / entry_id
        entry_root.mkdir()

        target = entry_root / "harness"
        metadata = {
            "id": entry_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "version": str(harness.version),
            "domain": str(domain),
            "task_shape": str(task_shape),
            "status": "pending",
            "experience": experience,
            "components": experience.get("components", []) if isinstance(experience, dict) else [],
            "path": str(target),
            "harness_path": str(target),
            "entry_path": str(entry_root),
        }
        try:
            shutil.copytree(source, target)
            (entry_root / "EXPERIENCE.md").write_text(
                "# Improvement experience (pending)\n\n```json\n" + json.dumps(experience, indent=2) + "\n```\n",
                encoding="utf-8",
            )
            # Store pending entries in a separate index
            pending_index = self.root / "pending_index.json"
            if pending_index.exists():
                pending = json.loads(pending_index.read_text(encoding="utf-8"))
            else:
                pending = []
            pending.append(metadata)
            pending_index.write_text(json.dumps(pending, indent=2), encoding="utf-8")
        except Exception:
            if entry_root.exists():
                shutil.rmtree(entry_root)
            raise
        return metadata

    def adopt(self, entry_id: str) -> dict | None:
        """Adopt a pending entry, moving it to the正式 library and removing from pending."""
        import shutil

        pending_index = self.root / "pending_index.json"
        if not pending_index.exists():
            return None

        pending = json.loads(pending_index.read_text(encoding="utf-8"))
        entry = next((e for e in pending if e["id"] == entry_id), None)
        if not entry:
            return None

        # Remove from pending
        pending = [e for e in pending if e["id"] != entry_id]
        pending_index.write_text(json.dumps(pending, indent=2), encoding="utf-8")

        # Add to正式 library
        source = Path(entry["harness_path"]).resolve()
        metadata = self.add(source, entry["experience"], entry["domain"],
                            entry["task_shape"], version=entry["version"])
        metadata["adopted_from"] = entry_id

        # Clean up pending entry
        entry_root = Path(entry["entry_path"])
        if entry_root.exists():
            shutil.rmtree(entry_root)

        return metadata

    def list_pending(self) -> list[dict]:
        """Return all pending library entries."""
        pending_index = self.root / "pending_index.json"
        if not pending_index.exists():
            return []
        return json.loads(pending_index.read_text(encoding="utf-8"))

    def inspect(self, entry_id: str) -> dict | None:
        """Return metadata and file names without importing candidate modules."""
        entry = self.get(entry_id)
        if entry is None:
            return None
        root = Path(entry["harness_path"])
        if root.is_symlink() or (hasattr(root, "is_junction") and root.is_junction()):
            raise ValueError("Unsafe library harness path")
        if not root.resolve().is_relative_to(self.root):
            raise ValueError("Library harness path escapes the library")
        files = []
        for path in root.rglob("*"):
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError("Unsafe link in stored harness")
            if path.is_file():
                files.append(str(path.relative_to(root)))
        return {**entry, "files": sorted(files)}
