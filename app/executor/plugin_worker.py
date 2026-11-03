"""Invoke one named harness plugin hook in its own Python process."""
from __future__ import annotations

import contextlib
import inspect
import json
import sys


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        with contextlib.redirect_stdout(sys.stderr):
            namespace = {"__name__": "harness_plugin"}
            exec(compile(payload["code"], "<harness plugin>", "exec"), namespace)
            hook = namespace.get(payload["hook"])
            output = hook(payload["context"]) if hook is not None else None
            if inspect.isawaitable(output):
                raise TypeError("Plugin hooks must be synchronous functions")
        print(json.dumps({"success": True, "output": output}))
    except Exception as exc:
        print(json.dumps({"success": False, "error": f"{type(exc).__name__}: {exc}"}))


if __name__ == "__main__":
    main()
