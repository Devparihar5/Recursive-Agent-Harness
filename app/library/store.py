"""Complete harness snapshots with a data-only metadata inspection API."""
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .index import LibraryIndex
from .retrieval import rank


class ImprovementLibrary:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.index = LibraryIndex(self.root)

    def add(self, harness, experience: dict, domain: str, task_shape: str) -> dict:
        # Validate metadata before creating any persistent artifacts.
        experience = json.loads(json.dumps(experience, allow_nan=False))
        source = Path(harness.path).resolve()
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
            "version": str(harness.version),
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
        selected = rank(self.list_entries(), task, limit)
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
