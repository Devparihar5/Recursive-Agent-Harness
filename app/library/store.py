"""Complete harness snapshots with embedding-based metadata retrieval."""
import json
import logging
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.harness.loader import load_harness
from app.harness.versioning import diff_harnesses
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
            version: str | None = None, adopted_from: str | None = None) -> dict:
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
        if adopted_from:
            metadata["adopted_from"] = adopted_from
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

    def _entry_root(self, entry: dict) -> Path:
        path = Path(entry["entry_path"])
        resolved = path.resolve()
        if (not resolved.is_relative_to(self.root) or resolved == self.root
                or len(resolved.relative_to(self.root).parts) != 2
                or not re.fullmatch(r"entry_[0-9]{3,}", resolved.name)
                or Path(entry["harness_path"]).resolve() != resolved / "harness"):
            raise ValueError("Unsafe library entry path")
        for item in (path, path.parent, path / "harness"):
            if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                raise ValueError("Unsafe link in library entry path")
        return resolved

    def _enrich_entry(self, entry: dict) -> dict:
        root = self._entry_root(entry)
        marker = root / "ARCHIVED.json"
        annotations_dir = root / "annotations"
        if (marker.is_symlink() or annotations_dir.is_symlink()
                or (hasattr(annotations_dir, "is_junction") and annotations_dir.is_junction())):
            raise ValueError("Unsafe link in library metadata")
        annotations = []
        if annotations_dir.is_dir():
            for path in sorted(annotations_dir.glob("*.json")):
                if path.is_symlink():
                    raise ValueError("Unsafe annotation link")
                annotations.append(json.loads(path.read_text(encoding="utf-8")))
        return {**entry, "archived": marker.is_file(), "annotations": annotations}

    def list_entries(self, include_archived: bool = False) -> list[dict]:
        entries = [self._enrich_entry(entry) for entry in self.index.list_entries()]
        return entries if include_archived else [entry for entry in entries if not entry["archived"]]

    def search_entries(self, query: str = "", domain: str = "", component: str = "",
                       include_archived: bool = False) -> list[dict]:
        query, domain, component = query.casefold(), domain.casefold(), component.casefold()
        return [entry for entry in self.list_entries(include_archived=include_archived)
                if (not query or query in json.dumps(entry, ensure_ascii=False).casefold())
                and (not domain or str(entry.get("domain", "")).casefold() == domain)
                and (not component or any(component in str(item).casefold()
                                          for item in entry.get("components", [])))]

    def diff_from_base(self, entry_id: str, base_path: Path) -> str | None:
        entry = self.inspect(entry_id)
        if entry is None:
            return None
        return diff_harnesses(load_harness(base_path), load_harness(entry["harness_path"]))

    def get(self, entry_id: str) -> dict | None:
        if re.fullmatch(r"[0-9a-f]{32}", entry_id):
            entry = self.index.get(entry_id)
            if entry is None:
                return None
            enriched = self._enrich_entry(entry)
            return None if enriched["archived"] else enriched
        if re.fullmatch(r"entry_[0-9]{3,}", entry_id):
            matches = [entry for entry in self.list_entries()
                       if Path(entry["entry_path"]).name == entry_id]
            return matches[0] if len(matches) == 1 else None
        return None

    def annotate(self, entry_id: str, note: str) -> dict | None:
        if not isinstance(note, str) or not note.strip() or len(note) > 8000:
            raise ValueError("Annotation must be nonempty text of at most 8000 characters")
        entry = self.get(entry_id)
        if entry is None:
            return None
        directory = self._entry_root(entry) / "annotations"
        if directory.is_symlink() or (hasattr(directory, "is_junction") and directory.is_junction()):
            raise ValueError("Unsafe annotation directory")
        directory.mkdir(exist_ok=True)
        annotation = {"note": note.strip(), "created_at": datetime.now(timezone.utc).isoformat()}
        path = directory / f"{uuid.uuid4().hex}.json"
        temporary = path.with_suffix(".tmp")
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(annotation, stream, ensure_ascii=False)
        temporary.replace(path)
        try:
            self._write_domain_index(directory.parent.parent, entry["domain"])
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return annotation

    def archive(self, entry_id: str, reason: str = "") -> dict | None:
        if not isinstance(reason, str) or len(reason) > 8000:
            raise ValueError("Archive reason must be text of at most 8000 characters")
        entry = self.get(entry_id)
        if entry is None:
            return None
        marker = self._entry_root(entry) / "ARCHIVED.json"
        data = {"reason": reason.strip(), "archived_at": datetime.now(timezone.utc).isoformat()}
        with marker.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False)
        try:
            self._write_domain_index(marker.parent.parent, entry["domain"])
        except Exception:
            marker.unlink(missing_ok=True)
            raise
        return {"id": entry["id"], "archived": True}

    def restore(self, entry_id: str) -> dict | None:
        if not re.fullmatch(r"[0-9a-f]{32}", entry_id):
            raise ValueError("Invalid library entry identifier")
        entry = self.index.get(entry_id)
        if entry is None:
            return None
        marker = self._entry_root(entry) / "ARCHIVED.json"
        if marker.is_symlink() or not marker.is_file():
            return None
        old_marker = marker.read_bytes()
        marker.unlink()
        try:
            self._write_domain_index(marker.parent.parent, entry["domain"])
        except Exception:
            with marker.open("xb") as stream:
                stream.write(old_marker)
            raise
        return {"id": entry_id, "archived": False}

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
                    eligible = {entry["id"] for entry in all_entries}
                    vector_results = [entry for entry in self.index.search(query_vector, limit=limit * 2)
                                      if entry.get("id") in eligible]
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

    def adopt(self, entry_id: str, note: str = "") -> dict | None:
        """Adopt a pending entry, moving it to the正式 library and removing from pending."""

        if not re.fullmatch(r"[0-9a-f]{32}", entry_id):
            raise ValueError("Invalid pending entry identifier")
        if not isinstance(note, str) or len(note) > 8000:
            raise ValueError("Adoption note must be text of at most 8000 characters")
        pending_index = self.root / "pending_index.json"
        if not pending_index.exists():
            return None

        pending = json.loads(pending_index.read_text(encoding="utf-8"))
        entry = next((e for e in pending if e["id"] == entry_id), None)
        if not entry:
            return None

        pending_root = self.root / "pending"
        pending_entry = pending_root / entry_id
        if any(path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())
               for path in (pending_root, pending_entry, pending_entry / "harness")):
            raise ValueError("Unsafe link in pending harness path")
        source = Path(entry["harness_path"]).resolve()
        entry_root = Path(entry["entry_path"]).resolve()
        expected = pending_entry.resolve()
        if (not expected.is_relative_to(self.root) or expected.parent != pending_root.resolve()
                or entry_root != expected or source != expected / "harness"):
            raise ValueError("Unsafe pending harness path")
        experience = dict(entry["experience"])
        if note.strip():
            experience["adoption_note"] = note.strip()
        metadata = self.add(source, experience, entry["domain"], entry["task_shape"],
                            version=entry["version"], adopted_from=entry_id)

        pending = [e for e in pending if e["id"] != entry_id]
        temporary = pending_index.with_suffix(".tmp")
        temporary.write_text(json.dumps(pending, indent=2), encoding="utf-8")
        temporary.replace(pending_index)

        # Clean up pending entry
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
