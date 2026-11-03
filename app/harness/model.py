from pathlib import Path
import hashlib
import re
from pydantic import BaseModel, ConfigDict, Field
from app.core.models import SubAgentDefinition


def harness_sha256(files: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for name, text in sorted(files.items()):
        digest.update(name.encode() + b"\x00" + text.encode() + b"\x00")
    return digest.hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    root = Path(root).resolve()
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or ":" in relative or "\\" in relative:
        raise ValueError(f"Unsafe harness path: {relative}")
    result = (root / rel).resolve()
    if not result.is_relative_to(root):
        raise ValueError(f"Harness path escapes root: {relative}")
    return result


class Harness(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    path: Path
    version: str = ""
    files: dict[str, str] = Field(default_factory=dict)

    def read(self, name: str = "systemprompt.md") -> str:
        if name in self.files:
            return self.files[name]
        return safe_path(self.path, name).read_text(encoding="utf-8")

    @property
    def system_prompt(self) -> str:
        return "\n\n".join(f"# {name}\n{text}" for name, text in sorted(self.files.items())
                         if name in {"systemprompt.md", "guardrails.md", "LongTermMEMORY.md", "tool_guidance.md"})

    def active_skills(self, task) -> dict[str, str]:
        text = f"{task.domain} {task.text}".lower().replace("_", " ")
        active = {}
        for name, content in self.files.items():
            path = Path(name)
            if len(path.parts) != 3 or path.parts[0] != "skills" or path.name != "SKILL.md":
                continue
            skill_name = path.parent.name.lower().replace("_", " ")
            trigger_line = next((line for line in content.splitlines()
                                 if re.match(r"(?i)^\s*(triggers?|activation):", line)), "")
            triggers = [word.strip().lower() for word in re.split(r"[,;]", trigger_line.split(":", 1)[-1])]
            if (skill_name in text or path.parent.name.lower() in {"general", "default"}
                    or any(trigger and trigger in text for trigger in triggers)):
                active[name] = content
        return active

    def subagents(self):
        """Expose definitions as data for a separate-context adapter."""
        definitions = {}
        for name, content in self.files.items():
            path = Path(name)
            if len(path.parts) == 3 and path.parts[0] == "sub_agents" and path.name == "AGENT.md":
                trigger_line = next((line for line in content.splitlines()
                                     if re.match(r"(?i)^\s*triggers?:", line)), "")
                triggers = [word.strip() for word in trigger_line.split(":", 1)[-1].split(",")
                            if word.strip()]
                tools_line = next((line for line in content.splitlines()
                                   if re.match(r"(?i)^\s*tools:\s*", line)), "")
                allowed_tools = [word.strip() for word in tools_line.split(":", 1)[-1].split(",")
                                 if word.strip()]
                definitions[path.parent.name] = SubAgentDefinition(
                    name=path.parent.name, instructions=content, triggers=triggers,
                    allowed_tools=allowed_tools)
        return definitions
