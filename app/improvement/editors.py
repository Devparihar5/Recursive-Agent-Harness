"""Declarative, confined harness editing; model output is never executed."""
import json
import shutil
from pathlib import Path
from uuid import uuid4

from app.core.models import HarnessCandidate
from app.harness.loader import load_harness, safe_path
from app.harness.versioning import clone_harness, diff_harnesses
from .utils import ask_json


class HarnessEditor:
    def __init__(self, provider, workspace, kind="invariant", retries=1):
        self.provider = provider
        self.workspace = Path(workspace)
        self.kind = kind
        self.retries = retries

    async def edit(self, task, harness, history, experiences):
        candidate_id = uuid4().hex
        destination = self.workspace / candidate_id
        source = Path(harness.path)
        errors = []
        patches = []
        for attempt in range(self.retries + 1):
            try:
                result = await ask_json(self.provider,
                    "Improve a complete agent harness using declarative file replacements. "
                    "Return {patches:[{path:relative_file_path,content:complete_file_text}],reasoning:string}. "
                    "Required files: systemprompt.md, guardrails.md, LongTermMEMORY.md, tool_guidance.md. "
                    "Optional artifacts: skills/*/SKILL.md, sub_agents/*/AGENT.md, "
                    "scripts/*.py and plugins/*.py. Python files are inert source artifacts. "
                    "Preserve every required file and existing unrelated behavior. "
                    + ("Improve general task-independent reasoning and verification." if self.kind == "invariant"
                       else "Improve domain-specific procedures grounded in the task and observed failures."),
                    {"task": task, "history": history, "experiences": experiences,
                     "files": self._files(source), "validation_errors": errors})
                patches = result.get("patches")
                if not isinstance(patches, list) or not patches:
                    raise ValueError("At least one declarative patch is required")
                if destination.exists():
                    shutil.rmtree(destination)
                clone_harness(harness, destination)
                for patch in patches:
                    self._apply(destination, patch)
                self._validate(source, destination)
                loaded = load_harness(destination)
                return HarnessCandidate(id=candidate_id, candidate_id=candidate_id,
                    scope=self.kind.upper(), base_harness_version=harness.version,
                    modified_harness_path=str(destination), diff=diff_harnesses(harness, loaded),
                    reasoning=str(result.get("reasoning", "")), harness_path=str(destination),
                    path=str(destination), parent_version=harness.version,
                    version=loaded.version, editor=self.kind, changes=patches,
                    validation_errors=[], valid=True)
            except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as exc:
                errors.append(str(exc))
        return HarnessCandidate(id=candidate_id, candidate_id=candidate_id, scope=self.kind.upper(),
            base_harness_version=harness.version, modified_harness_path=str(destination),
            harness_path=str(destination), version=candidate_id,
            editor=self.kind, changes=patches if isinstance(patches, list) else [],
            validation_errors=errors, valid=False)

    @staticmethod
    def _files(root):
        return {str(path.relative_to(root)): path.read_text(encoding="utf-8")
                for path in root.rglob("*") if path.is_file() and not path.is_symlink()
                and path.suffix.lower() in {".md", ".py"}}

    @staticmethod
    def _apply(root, patch):
        relative = Path(patch["path"])
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("Patch path must stay inside the harness")
        target = safe_path(root, patch["path"])
        python_artifact = (target.suffix.lower() == ".py" and len(relative.parts) == 2
                           and relative.parts[0] in {"scripts", "plugins"})
        if target.suffix.lower() != ".md" and not python_artifact:
            raise ValueError("Only declarative harness files may be edited")
        if target.is_symlink() or any(parent.is_symlink() for parent in target.parents):
            raise ValueError("Symlink patch targets are forbidden")
        if not isinstance(patch["content"], str) or not patch["content"].strip():
            raise ValueError("Patch content must be nonempty text")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(patch["content"], encoding="utf-8")

    @staticmethod
    def _validate(source, destination):
        for name in ("systemprompt.md", "guardrails.md", "LongTermMEMORY.md", "tool_guidance.md"):
            target = destination / name
            if not target.is_file() or not target.read_text(encoding="utf-8").strip():
                raise ValueError(f"Required harness file is missing or empty: {name}")
        for path in source.rglob("*"):
            if path.is_symlink():
                raise ValueError("Harness symlinks are forbidden")
            if path.is_file() and not (destination / path.relative_to(source)).is_file():
                raise ValueError("Candidate is missing an original harness file")
        for path in destination.rglob("*.json"):
            json.loads(path.read_text(encoding="utf-8"))
        if not any(destination.rglob("*.md")):
            raise ValueError("Harness requires markdown instructions")


class InvariantEditor(HarnessEditor):
    def __init__(self, provider, workspace, retries=1):
        super().__init__(provider, workspace, "invariant", retries)


class DomainEditor(HarnessEditor):
    def __init__(self, provider, workspace, retries=1):
        super().__init__(provider, workspace, "domain", retries)
