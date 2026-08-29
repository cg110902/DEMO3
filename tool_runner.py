"""Public, side-effect-aware command runner for Universal Novel Studio.

This module is deliberately a thin Python/LLM boundary: it invokes the public
``studio.py`` CLI without importing internal tool modules or touching SSOT files.
It is safe for integrations that need one consistent subprocess contract.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ToolResult:
    """Normalized subprocess result; stdout/stderr remain lossless strings."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def json(self) -> Any:
        """Decode JSON stdout, raising ValueError when the command is not JSON."""
        return json.loads(self.stdout)


def run(
    args: Sequence[str],
    *,
    workspace: str | os.PathLike[str] | None = None,
    timeout: float = 120.0,
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> ToolResult:
    """Run a public studio command without shell interpolation.

    ``args`` excludes the Python executable and ``studio.py``.  A workspace is
    passed as the public ``--workspace`` option.  No LLM call is made here.
    """
    if not args or any(not isinstance(item, str) for item in args):
        raise ValueError("args must be a non-empty sequence of strings")
    command = (sys.executable, "studio.py", *args)
    if workspace is not None:
        command += ("--workspace", str(Path(workspace)))
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=None if env is None else {**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return ToolResult(command, completed.returncode, completed.stdout, completed.stderr)


__all__ = ["ToolResult", "run"]
