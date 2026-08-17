from __future__ import annotations

import sys

import pytest

from reqgraph.exec.test_runner import CommandTimeoutError, run_test_command


def test_run_test_command_success(tmp_path):
    result = run_test_command(tmp_path, f"{sys.executable} -c \"import sys; sys.exit(0)\"")
    assert result.passed
    assert result.exit_code == 0


def test_run_test_command_failure(tmp_path):
    result = run_test_command(tmp_path, f"{sys.executable} -c \"import sys; sys.exit(1)\"")
    assert not result.passed
    assert result.exit_code == 1


def test_run_test_command_captures_stdout_stderr(tmp_path):
    result = run_test_command(
        tmp_path,
        f"{sys.executable} -c \"import sys; print('out'); print('err', file=sys.stderr); sys.exit(1)\"",
    )
    assert "out" in result.stdout
    assert "err" in result.stderr


def test_run_test_command_runs_in_given_cwd(tmp_path):
    marker = tmp_path / "marker.txt"
    marker.write_text("hi")
    result = run_test_command(
        tmp_path,
        f"{sys.executable} -c \"import pathlib, sys; sys.exit(0 if pathlib.Path('marker.txt').exists() else 1)\"",
    )
    assert result.passed


def test_run_test_command_times_out(tmp_path):
    with pytest.raises(CommandTimeoutError):
        run_test_command(tmp_path, f"{sys.executable} -c \"import time; time.sleep(5)\"", timeout=1)


def test_run_test_command_never_uses_shell_true(tmp_path):
    # A command string containing shell metacharacters must be treated as
    # literal argv entries, never interpreted by a shell. shlex.split turns
    # "; echo pwned" into inert trailing argv for python's -c (ending up in
    # sys.argv, unused) rather than a second shell command — so the real
    # proof of no injection is that "pwned" is never actually executed/printed,
    # not the exit code (python -c happily ignores extra positional argv).
    result = run_test_command(tmp_path, f"{sys.executable} -c \"import sys; sys.exit(0)\" ; echo pwned")
    assert result.exit_code == 0
    assert "pwned" not in result.stdout
