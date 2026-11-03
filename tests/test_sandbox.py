import asyncio
from pathlib import Path

from app.core.config import Settings
from app.executor.sandbox import PluginRunner, ScriptExecutor, validate_python_ast, validate_script_path


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    (workspace / "scripts").mkdir(parents=True, exist_ok=True)
    (workspace / "plugins").mkdir(parents=True, exist_ok=True)
    return workspace


def test_validate_python_ast_rejects_unsafe_constructs():
    assert validate_python_ast("print('safe')") == []
    assert validate_python_ast("import json\nprint(json.dumps({'ok': True}))") == []
    assert validate_python_ast("import requests\nprint(requests.get('http://example.com'))") != []
    assert validate_python_ast("eval('1 + 1')") != []


def test_validate_script_path_allows_workspace_and_rejects_escape(tmp_path: Path):
    workspace = _workspace(tmp_path)
    inside = workspace / "scripts" / "tool.py"
    inside.write_text("print('safe')", encoding="utf-8")
    assert validate_script_path(inside, workspace) is True
    escape = tmp_path / "evil.py"
    escape.write_text("print('unsafe')", encoding="utf-8")
    assert validate_script_path(escape, workspace) is False


def test_script_executor_runs_safe_script(tmp_path: Path):
    workspace = _workspace(tmp_path)
    script = workspace / "scripts" / "tool.py"
    script.write_text("print('hello from script')", encoding="utf-8")
    executor = ScriptExecutor(Settings(), workspace)
    result = asyncio.run(executor.execute_script(script))
    assert result["success"] is True
    assert "hello from script" in result["stdout"]
    assert result["error"] is None


def test_script_executor_rejects_unsafe_script(tmp_path: Path):
    workspace = _workspace(tmp_path)
    script = workspace / "scripts" / "tool.py"
    script.write_text("import requests\nprint('nope')", encoding="utf-8")
    executor = ScriptExecutor(Settings(), workspace)
    result = asyncio.run(executor.execute_script(script))
    assert result["success"] is False
    assert result["returncode"] == -1
    assert "not allowed" in result["error"]


def test_script_executor_rejects_escape_and_reports_timeout(tmp_path: Path):
    workspace = _workspace(tmp_path)
    escape = tmp_path / "evil.py"
    escape.write_text("print('unsafe')", encoding="utf-8")
    executor = ScriptExecutor(Settings(), workspace)
    escaped = asyncio.run(executor.execute_script(escape))
    assert escaped["success"] is False
    assert "Path escape" in escaped["error"]

    sleeper = workspace / "scripts" / "sleeper.py"
    sleeper.write_text("import time\nprint('start')\ntime.sleep(30)", encoding="utf-8")
    timed_out = asyncio.run(executor.execute_script(sleeper, timeout=1))
    assert timed_out["success"] is False
    assert "timed out" in timed_out["error"]


def test_plugin_runner_executes_hook_in_sandbox(tmp_path: Path):
    workspace = _workspace(tmp_path)
    plugin = workspace / "plugins" / "before_tool.py"
    plugin.write_text(
        "import json\n"
        "import sys\n"
        "data = json.loads(sys.stdin.read())\n"
        "json.dump({'success': True, 'output': (data.get('context') or {}).get('tool')}, sys.stdout)\n",
        encoding="utf-8",
    )
    runner = PluginRunner(Settings(), workspace)
    result = asyncio.run(runner.run_hook(plugin, "before_tool", {"tool": "read_file", "arguments": {}}))
    assert result["success"] is True
    assert result["output"] == "read_file"
