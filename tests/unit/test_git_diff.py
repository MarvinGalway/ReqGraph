from __future__ import annotations

import subprocess

from reqgraph.extract.git_diff import (
    changed_files,
    current_revision,
    list_tracked_files,
    read_file_at_revision,
)


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init_two_commit_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "a.py").write_text("x = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "first")
    first_rev = current_revision(repo)

    (repo / "a.py").write_text("x = 2\n")
    (repo / "b.py").write_text("y = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "second")
    return repo, first_rev


def test_current_revision_and_list_tracked_files(tmp_path):
    repo, first_rev = _init_two_commit_repo(tmp_path)
    assert current_revision(repo) != first_rev
    assert set(list_tracked_files(repo)) == {"a.py", "b.py"}


def test_changed_files_between_revisions(tmp_path):
    repo, first_rev = _init_two_commit_repo(tmp_path)
    changed = changed_files(repo, first_rev, "HEAD")
    assert set(changed) == {"a.py", "b.py"}


def test_read_file_at_revision(tmp_path):
    repo, first_rev = _init_two_commit_repo(tmp_path)
    assert read_file_at_revision(repo, first_rev, "a.py") == "x = 1\n"
    assert read_file_at_revision(repo, "HEAD", "a.py") == "x = 2\n"
    assert read_file_at_revision(repo, first_rev, "b.py") is None
