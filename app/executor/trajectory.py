"""Helpers for inspecting persisted run trajectories."""
from __future__ import annotations

import json
from pathlib import Path


def load_trajectory(run_dir: str | Path) -> list[dict]:
    return json.loads((Path(run_dir) / "trajectory.json").read_text(encoding="utf-8"))
