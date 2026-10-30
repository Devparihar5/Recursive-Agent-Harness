from pathlib import Path
import re
from pydantic import BaseModel, ConfigDict, Field


class Harness(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    path: Path
    version: str = ""
    files: dict[str, str] = Field(default_factory=dict)

    def read(self, name: str = "systemprompt.md") -> str:
        from .loader import safe_path
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
        from app.core.models import SubAgentDefinition

        definitions = {}
        for name, content in self.files.items():
            path = Path(name)
            if len(path.parts) == 3 and path.parts[0] == "sub_agents" and path.name == "AGENT.md":
                trigger_line = next((line for line in content.splitlines()
                                     if re.match(r"(?i)^\s*triggers?:", line)), "")
                triggers = [word.strip() for word in trigger_line.split(":", 1)[-1].split(",")
                            if word.strip()]
                definitions[path.parent.name] = SubAgentDefinition(
                    name=path.parent.name, instructions=content, triggers=triggers)
        return definitions
