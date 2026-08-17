"""Runs a project's configured test command as a subprocess. Used by
`run-task --verify-red` and `complete`'s regression gate — this is graph-cli's
only place that executes code from the target repo, and it only ever runs a
command the project owner configured (`project.json.test_command` /
`--test-command`), the same trust model as CI. `shlex.split` + `check=False`,
never `shell=True` — same safe-subprocess pattern as `extract/git_diff.py`.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


class CommandTimeoutError(RuntimeError):
    pass


@dataclass
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


def run_test_command(repo_path: Path, command: str, timeout: int = 300) -> CommandResult:
    args = shlex.split(command)
    try:
        result = subprocess.run(
            args, cwd=repo_path, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as e:
        raise CommandTimeoutError(f"test command {command!r} exceeded {timeout}s timeout") from e
    return CommandResult(
        command=command, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr
    )
