"""Git-backed helpers for `bootstrap-scan`/`detect-changes`.

`detect-changes` diffs file lists via `git diff --name-only`, then hands each
changed file's old/new content to the AST extractor to compute a
`(path, symbol) -> hash` diff — the symbol-level change classification lives
in the CLI command, not here; this module only talks to git.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

_FIELD_SEP = "\x1f"  # ASCII unit separator — avoids collisions with '|' in commit subjects


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommitInfo:
    commit_hash: str
    author: str
    date: str
    subject: str


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


def file_commit_history(repo_path: Path, path: str, limit: int = 5) -> list[CommitInfo]:
    """File-level (not symbol-level — `git log -L` per-symbol history is
    expensive and out of scope) commit history, most recent first. Used by
    `bootstrap-scan` as optional historical provenance (spec §7 B0). Returns
    an empty list for a non-git repo or a path with no history, rather than
    raising — same graceful-degradation pattern as `bootstrap_scan.py`'s
    `_safe_revision`/`_list_all_tracked`.
    """
    try:
        output = _run_git(
            repo_path,
            ["log", f"-n{limit}", f"--format=%H{_FIELD_SEP}%an{_FIELD_SEP}%aI{_FIELD_SEP}%s", "--", path],
        )
    except GitError:
        return []
    commits = []
    for line in output.splitlines():
        parts = line.split(_FIELD_SEP)
        if len(parts) != 4:
            continue
        commit_hash, author, date, subject = parts
        commits.append(CommitInfo(commit_hash=commit_hash, author=author, date=date, subject=subject))
    return commits
