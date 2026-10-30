"""Data-only tool and middleware contracts for future sandbox integrations."""
from __future__ import annotations

from typing import Any, Protocol


class Tool(Protocol):
    name: str

    async def invoke(self, arguments: dict[str, Any]) -> dict[str, Any]: ...


class MiddlewarePlugin(Protocol):
    async def before_model_call(self, context: dict[str, Any]) -> None: ...
    async def after_model_call(self, context: dict[str, Any], response: str) -> None: ...
    async def before_tool_call(self, context: dict[str, Any], tool: str, arguments: dict[str, Any]) -> None: ...
    async def after_tool_call(self, context: dict[str, Any], tool: str, result: dict[str, Any]) -> None: ...
    async def before_task_complete(self, context: dict[str, Any], deliverable: str) -> None: ...


# A candidate's Python modules must not be imported into this process. A future
# sandbox adapter can implement these interfaces in a separate restricted process.
