"""Run harness code in subprocesses with path checks, AST checks and timeouts.

These checks do not provide OS-level isolation from the host filesystem.
"""
from __future__ import annotations

import asyncio
import ast
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.core.config import Settings


def validate_python_ast(code: str, allowed_modules: set[str] | None = None) -> list[str]:
    """Validate Python code has safe AST. Returns list of error messages (empty if OK)."""
    errors: list[str] = []
    allowed_modules = allowed_modules or {"time", "os", "pathlib", "json", "re", "subprocess", "sys"}

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        errors.append(f"Syntax error: {e}")
        return errors

    # Check imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in allowed_modules:
                    errors.append(f"Import of '{alias.name}' not allowed")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module not in allowed_modules:
                errors.append(f"Import from '{node.module}' not allowed")

    # Check for dangerous constructs
    dangerous = {"exec", "eval", "compile", "open", "__import__", "globals", "locals"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in dangerous:
                errors.append(f"Call to '{node.func.id}' is not allowed")
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in {"exec", "eval", "compile"}:
                    errors.append(f"Call to .{node.func.attr}() is not allowed")

    # Check for dangerous attributes
    dangerous_attrs = {"__globals__", "__builtins__", "__class__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr in dangerous_attrs:
                errors.append(f"Access to .{node.attr} is not allowed")

    return errors


def validate_script_path(path: Path, workspace: Path) -> bool:
    """Check that the script path is within allowed directories and doesn't escape."""
    try:
        resolved = path.resolve()
        workspace_resolved = workspace.resolve()
        return resolved.is_relative_to(workspace_resolved) and resolved.is_file()
    except (ValueError, OSError):
        return False


class ScriptExecutor:
    """Execute Python scripts in a sandboxed subprocess."""

    def __init__(self, settings: Settings, workspace: Path,
                 allowed_root: Path | None = None):
        self.settings = settings
        self.workspace = workspace.resolve()
        self.allowed_root = (allowed_root or workspace).resolve()

    async def execute_script(self, script_path: Path, args: list[str] | None = None,
                             timeout: float | None = None) -> dict[str, Any]:
        """Execute a Python script in a subprocess and return result.

        Returns:
            {"success": bool, "output": str, "error": str | None,
             "returncode": int, "stdout": str, "stderr": str}
        """
        if not validate_script_path(script_path, self.allowed_root):
            return {"success": False, "output": "", "error": "Path escape detected",
                    "returncode": -1, "stdout": "", "stderr": ""}

        errors = validate_python_ast(script_path.read_text(encoding="utf-8"))
        if errors:
            return {"success": False, "output": "", "error": "; ".join(errors),
                    "returncode": -1, "stdout": "", "stderr": ""}

        # Build a safe subprocess command
        python = sys.executable
        args = args or []
        cmd = [python, "-I", str(script_path), *args]

        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": "",
            "HOME": os.environ.get("HOME", ""),
            "TEMP": os.environ.get("TEMP", ""),
            "TMP": os.environ.get("TMP", ""),
            "SCRIPT_WORKSPACE": str(self.workspace),
            "SCRIPT_ID": script_path.stem,
        }

        timeout = timeout or float(getattr(self.settings, "timeout_seconds", 300))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(self.workspace),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
                return {
                    "success": proc.returncode == 0,
                    "output": stdout.decode("utf-8", errors="replace"),
                    "error": None if proc.returncode == 0 else stderr.decode("utf-8", errors="replace"),
                    "returncode": proc.returncode,
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                }
            except asyncio.CancelledError:
                if proc.returncode is None:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
                await proc.wait()
                raise
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return {
                    "success": False,
                    "output": "",
                    "error": f"Script timed out after {timeout}s",
                    "returncode": -2,
                    "stdout": "",
                    "stderr": "",
                }
        except Exception as exc:
            return {
                "success": False,
                "output": "",
                "error": f"Execution failed: {exc}",
                "returncode": -3,
                "stdout": "",
                "stderr": "",
            }


class PluginRunner:
    """Run middleware plugins via subprocess.

    Plugins implement the MiddlewareProtocol and receive context via stdin JSON.
    They write results to stdout JSON.
    """
    def __init__(self, settings: Settings, workspace: Path,
                 allowed_root: Path | None = None):
        self.settings = settings
        self.workspace = workspace.resolve()
        self.allowed_root = (allowed_root or workspace).resolve()

    async def run_hook(self, plugin_path: Path, hook: str,
                       context: dict[str, Any]) -> dict[str, Any]:
        """Execute a plugin hook in a subprocess.

        Plugin must handle JSON input on stdin:
            {"hook": "hook_name", "context": {...}}
        And write JSON output on stdout:
            {"success": bool, "output": any, "error": str | None}
        """
        if not plugin_path.exists():
            return {"success": False, "output": None, "error": f"Plugin not found: {plugin_path}"}

        if not validate_script_path(plugin_path, self.allowed_root):
            return {"success": False, "output": None, "error": "Path escape detected"}

        code = plugin_path.read_text(encoding="utf-8")
        errors = validate_python_ast(code)
        if errors:
            return {"success": False, "output": None, "error": "; ".join(errors)}

        python = sys.executable
        # Harness plugins define named hooks. Keep the older stdin/stdout
        # executable protocol for callers that supply a standalone plugin.
        functions = {node.name for node in ast.parse(code).body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        payload = json.dumps({"hook": hook, "context": context,
                              **({"code": code} if functions else {})})
        cmd = ([python, "-I", str(Path(__file__).with_name("plugin_worker.py"))]
               if functions else [python, "-I", str(plugin_path)])

        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": "",
            "HOME": os.environ.get("HOME", ""),
            "TEMP": os.environ.get("TEMP", ""),
            "TMP": os.environ.get("TMP", ""),
        }

        timeout = float(getattr(self.settings, "timeout_seconds", 300))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(self.workspace),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=payload.encode("utf-8")),
                    timeout=timeout,
                )
                result = json.loads(stdout.decode("utf-8", errors="replace"))
                return {
                    "success": result.get("success", False),
                    "output": result.get("output"),
                    "error": result.get("error"),
                }
            except asyncio.CancelledError:
                if proc.returncode is None:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
                await proc.wait()
                raise
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return {
                    "success": False,
                    "output": None,
                    "error": f"Plugin hook '{hook}' timed out after {timeout}s",
                }
            except json.JSONDecodeError as exc:
                return {
                    "success": False,
                    "output": None,
                    "error": (f"Plugin output not valid JSON: {exc}; "
                              f"stderr: {stderr.decode('utf-8', errors='replace')[:1000]}"),
                }
        except Exception as exc:
            return {
                "success": False,
                "output": None,
                "error": f"Plugin execution failed: {exc}",
            }
