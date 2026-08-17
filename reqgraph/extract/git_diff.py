"""Git-backed helpers for `bootstrap-scan`/`detect-changes`.

`detect-changes` diffs file lists via `git diff --name-only`, then hands each
changed file's old/new content to the AST extractor to compute a
`(path, symbol) -> hash` diff — the symbol-level change classification lives
in the CLI command, not here; this module only talks to git.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def _run_git(repo_path: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_path, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def current_revision(repo_path: Path) -> str:
    return _run_git(repo_path, ["rev-parse", "HEAD"]).strip()


def list_tracked_files(repo_path: Path, suffix: str = ".py") -> list[str]:
    output = _run_git(repo_path, ["ls-files"])
    return [line for line in output.splitlines() if line.endswith(suffix)]


def changed_files(repo_path: Path, old_rev: str, new_rev: str = "HEAD") -> list[str]:
    output = _run_git(repo_path, ["diff", "--name-only", old_rev, new_rev])
    return [line for line in output.splitlines() if line]


def read_file_at_revision(repo_path: Path, rev: str, path: str) -> str | None:
    try:
        return _run_git(repo_path, ["show", f"{rev}:{path}"])
    except GitError:
        return None
